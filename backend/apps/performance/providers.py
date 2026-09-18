"""Performance providers are separate from publishing capabilities."""

import re
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record
from apps.integrations.crypto import unseal
from apps.performance.models import Deployment, PerformanceSnapshot
from apps.performance.services import normalized
from apps.storage.google import ProviderFailure

CAPABILITIES = {
    "meta": {"performance_sync": True, "publishing": True},
    "tiktok": {"performance_sync": False, "publishing": False},
    "google_ads": {"performance_sync": False, "publishing": False},
    "youtube": {"performance_sync": False, "publishing": True},
}


class MetaPerformanceProvider:
    def sync(self, connection):
        secret = unseal(connection.credentials_encrypted)
        version = secret.get("api_version", "")
        if not re.fullmatch(r"v\d+\.\d+", version):
            raise ProviderFailure("Configure a supported Meta API version.")
        headers = {"Authorization": "Bearer " + secret.get("access_token", "")}
        for deployment in Deployment.objects.filter(connection=connection).exclude(ad_id=""):
            if not re.fullmatch(r"\d+", deployment.ad_id):
                raise ProviderFailure("Invalid Meta ad ID.")
            url = f"https://graph.facebook.com/{version}/{deployment.ad_id}/insights"
            params = {
                "fields": "date_start,date_stop,spend,impressions,reach,clicks,actions,action_values,account_currency",
                "date_preset": "last_30d",
                "time_increment": "1",
                "limit": "100",
            }
            while True:
                try:
                    response = httpx.get(
                        url,
                        headers=headers,
                        params=params,
                        timeout=settings.PROVIDER_TIMEOUT,
                        follow_redirects=False,
                    )
                    if response.status_code != 200:
                        raise ProviderFailure(
                            f"Meta performance returned HTTP {response.status_code}."
                        )
                    payload = response.json()
                except (httpx.HTTPError, ValueError):
                    raise ProviderFailure("Meta performance sync failed.") from None
                for item in payload.get("data", []):
                    start = datetime.fromisoformat(item["date_start"]).replace(
                        tzinfo=dt_timezone.utc
                    )
                    end = datetime.fromisoformat(item["date_stop"]).replace(
                        tzinfo=dt_timezone.utc
                    ) + timedelta(days=1)
                    actions = {
                        a["action_type"]: Decimal(a["value"]) for a in item.get("actions", [])
                    }
                    values = {
                        a["action_type"]: Decimal(a["value"]) for a in item.get("action_values", [])
                    }
                    numbers = {
                        key: Decimal(str(item.get(key, 0)))
                        for key in ["spend", "impressions", "reach", "clicks"]
                    }
                    numbers.update(
                        conversions=int(actions.get("purchase", 0)),
                        purchases=int(actions.get("purchase", 0)),
                        link_clicks=int(actions.get("link_click", 0)),
                        revenue=values.get("purchase", Decimal(0)),
                    )
                    with transaction.atomic():
                        # A duplicate window keeps its original immutable observation.
                        PerformanceSnapshot.objects.get_or_create(
                            deployment=deployment,
                            interval_start=start,
                            interval_end=end,
                            defaults={
                                "workspace": deployment.workspace,
                                "brand": deployment.brand,
                                "provider": "meta",
                                "currency": item.get("account_currency", "USD"),
                                "metrics": normalized(numbers),
                                **numbers,
                            },
                        )
                paging = payload.get("paging", {})
                after = paging.get("cursors", {}).get("after")
                if not paging.get("next") or not after:
                    break
                params["after"] = after
            deployment.last_sync = timezone.now()
            deployment.save(update_fields=["last_sync"])
        connection.last_sync = timezone.now()
        connection.last_error = ""
        connection.save(update_fields=["last_sync", "last_error"])
        record(connection.created_by, connection, "performance_synced")


def sync(connection):
    if connection.provider != "meta":
        raise ProviderFailure(
            "Performance synchronization is not implemented for this provider. Use manual snapshots."
        )
    MetaPerformanceProvider().sync(connection)
