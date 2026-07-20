# myapp/cron.py
import json
import logging
import time

import jwt
import requests
from django.db import transaction

from app.chatgpt.models import ChatgptAccount
from app.settings import CHATGPT_GATEWAY_URL
from app.settings import GATEWAY_ADMIN_SECRET

logger = logging.getLogger("cron")
DEFAULT_REFRESH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
REFRESH_WINDOW_SECONDS = 100 * 60


def _access_token_is_fresh(access_token):
    try:
        at_info = jwt.decode(access_token, options={"verify_signature": False})
        return int(time.time()) < at_info["exp"] - REFRESH_WINDOW_SECONDS
    except Exception:
        return False


def _update_token(chatgpt_username, chatgpt_token, client_id=None):
    url = CHATGPT_GATEWAY_URL + "/api/get-user-info"
    headers = {
        "Authorization": "Bearer {}".format(GATEWAY_ADMIN_SECRET),
    }
    payload = {"chatgpt_token": chatgpt_token}
    if client_id:
        payload = {
            "auth_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": chatgpt_token,
        }
    res = requests.post(url, headers=headers, json=payload)
    res_json = res.json()

    if res.status_code != 200:
        logger.info("token 更新失败: %s %s", chatgpt_username, json.dumps(res_json))
        message = res_json.get("message", "") if isinstance(res_json, dict) else str(res_json)
        if (
            "token 失效" in message
            or "authentication token" in message
            or "refresh_token" in message
        ):
            logger.warning("token 失效 %s", json.dumps(res_json))
            return False
        return None

    res_json["auth_status"] = True
    ChatgptAccount.save_data(res_json)
    return True


def update_access_token():
    for line in ChatgptAccount.objects.all():
        if _access_token_is_fresh(line.access_token) and line.auth_status:
            continue

        if line.refresh_token:
            with transaction.atomic():
                locked = ChatgptAccount.objects.select_for_update().get(id=line.id)
                if _access_token_is_fresh(locked.access_token) and locked.auth_status:
                    continue

                client_id = locked.refresh_client_id or DEFAULT_REFRESH_CLIENT_ID
                update_status = _update_token(locked.chatgpt_username, locked.refresh_token, client_id)
                if update_status is False:
                    expired_refresh_token = locked.refresh_token
                    locked.refresh_token = None
                    locked.save()
                    logger.warning(f"refresh_token 已经过期: {locked.chatgpt_username}, rtoken: {expired_refresh_token}")

        elif line.session_token:
            update_status = _update_token(line.chatgpt_username, line.session_token)
            if update_status is False:
                line.session_token = None
                line.save()
                logger.warning(f"session_token 已经过期: {line.chatgpt_username}, stoken: {line.session_token}")


def check_access_token():

    need_to_update = int(time.time() - 3600)
    for line in ChatgptAccount.objects.filter(updated_time__lte=need_to_update, auth_status=True).all():
        if line.access_token:
            if _update_token(line.chatgpt_username, line.access_token) is False:
                line.auth_status = False
                line.updated_time = int(time.time())
                line.save()
                logger.warning(f"access_token 已经过期: {line.chatgpt_username}")
                return
            else:
                line.updated_time = int(time.time())
                line.save()
                logger.info(f"access_token 有效: {line.chatgpt_username}")
