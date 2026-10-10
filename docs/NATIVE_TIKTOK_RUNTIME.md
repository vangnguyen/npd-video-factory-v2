# Native TikTok: cấu hình startup và đường HTTP

Phần này nối [backend async](NATIVE_TIKTOK_PUBLISHING.md) vào `LocalServer` và CLI hiện có. Nó dùng chung journal publication, Owner grant, private session, worker và queue. Quyền đọc creator được cấu hình riêng với quyền đăng. Studio đăng TikTok, provider thật, Owner UAT và toàn bộ Wave 9/Mode A/B vẫn chưa được nghiệm thu.

## Registry riêng, mặc định tắt

`--tiktok-publishing-registry` và `--enable-tiktok-creator-reads` giữ vai trò đọc account/creator hiện có. Companion `--tiktok-distribution-registry` phải nằm ngoài source/data root, cùng workspace và đúng fingerprint cấu hình creator. Schema:

```json
{
  "schema_version": "native-tiktok-distribution-registry-v1",
  "version": 1,
  "workspace_id": "WORKSPACE_ID",
  "bindings": [{
    "profile_id": "ppf_EXPLICIT_PROFILE",
    "expected_creator_configuration_sha256": "CURRENT_CREATOR_CONFIGURATION_SHA256",
    "gates": {
      "publish_enabled": false,
      "external_execution_enabled": false,
      "owner_gate_enabled": false
    }
  }]
}
```

Các giá trị in hoa là chỗ điền cấu hình, không phải dữ liệu chạy được. Token DPAPI tiếp tục nằm trong registry creator riêng; companion không chứa token, upload URI hoặc client graph. Startup kiểm tra metadata/fingerprint, không decrypt hoặc gọi provider.

`--enable-tiktok-distribution` mặc định false. Muốn bật runtime phải có human-auth registry, companion registry, creator reads và `--official-publish-session-directory` riêng ngoài source/data root. Ba gate trong companion cũng phải được bật rõ ràng. Cấu hình này vẫn chưa cấp grant đăng từng video: publication cần dry-run hợp lệ, draft creator đúng final/metadata, QC/rights/platform, Owner approval hữu hạn và các kiểm tra worker hiện tại.

`--enable-official-publish-queue` dùng chung queue cho YouTube và TikTok. Cấu hình TikTok hợp lệ không cần cấu hình YouTube. Queue vẫn mặc định tắt, có deadline/max steps và consent riêng. Không có retry tạo init/job trùng hoặc gửi lại chunk chưa xác định kết quả.

## Platform capability và lịch sử

`--publishing-capabilities-file` nhận cấu hình platform đã kiểm tra bên ngoài source/data root, tối đa 256 KiB, có human auth. Bỏ qua cờ này tiếp tục dùng cấu hình bundled hiện có. File được hash-bind; drift chặn approval/dispatch. Chọn file không bật gate hay chứng nhận platform/account/Owner thật. Fixture cố ý ghi rõ acceptance tổng hợp.

Google OAuth và TikTok có thể cùng được cấu hình: Google chỉ attach resolver vào binding Google đúng kiểu/purpose. Khi tắt hoặc bỏ cấu hình TikTok, lịch sử publication/job/receipt gốc vẫn đọc được mà không private load hoặc network. Cold startup không tự cấp quyền, decrypt, tiếp tục upload hoặc replay. Log queue giữ provider đúng nền tảng và chỉ field allowlisted; lỗi đọc metadata cho telemetry không thay kết quả bước đã hoàn tất.

## Bằng chứng và phần còn lại

[tiktok-runtime-evidence.json](north-star/tiktok-runtime-evidence.json) ghi log/hashes của HTTP/CLI/RBAC/CSRF/queue/default-off/history và hồi quy. HTTP, SQLite và DPAPI chạy local; response provider, media không phát được, Owner/platform acceptance là fixture. Không có provider thật, thao tác trả phí, bài đăng thật, merge main hoặc deployment. Test tạm được dọn theo `TemporaryDirectory`; log và source được giữ. Không có bundle media nghiệm thu mới trong increment này.

Tiếp theo: nối đúng reviewed draft/dry-run và tagged publication vào Studio; hỗ trợ profile/history/approval/queue/status/receipt TikTok mà giữ YouTube; hoàn thiện Meta, analytics và toàn bộ gap Master Spec. Quyền bật đăng thật, credentials/app eligibility/audit, rights/Owner/browser/provider acceptance và production vẫn cần bằng chứng riêng. Không thay trạng thái readiness toàn chương trình từ component này.
