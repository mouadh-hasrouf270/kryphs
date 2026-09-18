# Google Drive and YouTube setup

No Google account is connected by the demo. Live validation requires your Google Cloud project and authorized account.

1. Create/select a project in Google Cloud Console.
2. Enable Google Drive API. Enable YouTube Data API v3 if uploading videos.
3. Configure the OAuth consent screen, authorized domains, contact information and test users if the app remains in testing.
4. Create an OAuth **Web application** client. Add the exact redirect URI: local `http://127.0.0.1:5173/api/v1/google/callback/` or production `https://your-domain/api/v1/google/callback/`.
5. Put `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` and `GOOGLE_REDIRECT_URI` in `.env`. Set `APP_ENCRYPTION_KEY` independently from the Django signing key. Restart web and worker.
6. In Integrations → Storage, create a Google Drive connection for one workspace/brand. Use a dedicated account or a dedicated Shared Drive to avoid mixing brands in one inventory. Choose the root folder ID; for Shared Drives also provide the Shared Drive ID.
7. Open the connection and choose Connect Google. Default `file` uses `drive.file`; it only grants access to files created or explicitly authorized for the application. Choose `full` only when existing hierarchy browsing is necessary and the administrator has accepted the broader authorization.
8. To authorize YouTube, call the connection `connect` action with `{"scope":"file","youtube":true}` from an authenticated manager client. The current visual connect dialog exposes Drive scope; the YouTube scope toggle remains an API operation.
9. Complete Google consent. The server validates a one-use, ten-minute, user-bound state and PKCE challenge. Refresh credentials are encrypted before saving and are never returned to React.
10. Run the worker. Use Test connection, Sync inventory, or Create creative folders. Attach existing synced objects through Creative Files. Upload a local master through the creative detail screen; use the connection's transfer action with the version and target provider.
11. YouTube defaults to `private`; `unlisted` and explicit `public` are supported. Only an approved version with one active master is eligible. IDs are saved only from final confirmed responses.
12. To revoke access fully, remove the application's grant in your Google account security settings, then disconnect in CreativeManager. The app's Disconnect removes local credentials; it does not revoke the Google account grant remotely.

For company-owned binaries, prefer a Shared Drive: ownership remains with the organization. The current initial sync inventories files accessible through the configured connection, not only root-folder descendants. Use a narrowly scoped/dedicated connection until root-subtree filtering is added. Do not assign an unrestricted shared account inventory to a brand whose users should not see all those files.

Drive IDs are authoritative. Renames/moves update metadata without changing StorageObject identity. Deleted changes deactivate the object. The folder organizer currently creates durable per-creative root mappings; the full campaign/request/version folder hierarchy in the master specification remains incomplete.

Resumable uploads store encrypted session URIs and confirmed byte offsets. If initialization is uncertain, the worker refuses a blind restart. A final response without an external ID is a failure. Google API errors are sanitized; check provider quota, scope, consent/testing status and token revocation when reconnecting.

Official references used during implementation:

- [Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Drive upload protocols](https://developers.google.com/workspace/drive/api/guides/manage-uploads)
- [YouTube resumable uploads](https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol)
- [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Shared Drive support](https://developers.google.com/workspace/drive/api/guides/enable-shareddrives)

Google scope verification, app review, YouTube upload restrictions and account permissions depend on your project. Confirm them in the Google console before live use.
