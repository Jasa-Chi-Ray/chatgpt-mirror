"""Idempotent cleanup shared by upstream-account and automation-link actions."""
from django.db import transaction
from app.chatgpt.models import ChatgptAccount, ChatgptCar
from app.accounts.session_authority import gateway_authorization
from app.utils import get_request_subject, req_gateway


def disconnect_identity(request, identity_id, pool=True):
    if identity_id:
        req_gateway("post", "/api/web-login", json={"action": "disconnect", "id": identity_id,
            "pool": pool, "owner": get_request_subject(request), "authorization": gateway_authorization(request)})


@transaction.atomic
def delete_upstream_account(request, account):
    current = ChatgptAccount.objects.select_for_update().filter(pk=account.pk).first()
    if current is None:
        return
    disconnect_identity(request, current.web_identity_id, current.automation_owner_id is None)
    for car in ChatgptCar.objects.select_for_update():
        ids = car.gpt_account_list if isinstance(car.gpt_account_list, list) else []
        if str(current.pk) in {str(value) for value in ids}:
            car.gpt_account_list = [value for value in ids if str(value) != str(current.pk)]
            car.save(update_fields=["gpt_account_list"])
    current.delete()


def clear_automation_credentials(account):
    ChatgptAccount.objects.filter(pk=account.pk, web_identity_id=account.web_identity_id).update(
        web_identity_id=None, web_identity_version=0, access_token="", session_token=None,
        refresh_token=None, refresh_client_id=None, extra_cookies=[], access_token_valid=False,
        session_token_valid=False, auth_status=False, last_error="自动化链接已解除", usage_snapshot={}, usage_checked_at=None)
