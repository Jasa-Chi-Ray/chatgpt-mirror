import hashlib
import ipaddress
import json
import time
import uuid

import requests
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from requests.exceptions import RequestException
from rest_framework.exceptions import ValidationError

from app.accounts.models import VisitLog
from app.settings import CHATGPT_GATEWAY_URL, FREE_ACCOUNT_USERNAME
from app.settings import GATEWAY_ADMIN_SECRET

FREE_SESSION_SALT = "chatgpt-mirror.free-session.v1"
FREE_SESSION_MAX_AGE = 7 * 24 * 60 * 60


def generate_md5(input_string):
    md5_object = hashlib.md5()
    md5_object.update(input_string.encode('utf-8'))
    return md5_object.hexdigest()

def get_client_ip(request):
    candidates = (
        request.META.get("HTTP_X_CHATGPT_MIRROR_CLIENT_IP"),
        request.META.get("HTTP_CF_CONNECTING_IP"),
        request.META.get("HTTP_TRUE_CLIENT_IP"),
        request.META.get("HTTP_X_REAL_IP"),
        request.META.get("HTTP_X_FORWARDED_FOR"),
        request.META.get("REMOTE_ADDR"),
    )
    for candidate in candidates:
        if not candidate:
            continue
        for value in candidate.split(","):
            value = value.strip().strip("[]")
            try:
                return str(ipaddress.ip_address(value))
            except ValueError:
                continue
    return ""


def issue_free_session():
    return signing.dumps({"sid": uuid.uuid4().hex}, salt=FREE_SESSION_SALT, compress=True)


def get_request_subject(request):
    if request.user.username != FREE_ACCOUNT_USERNAME:
        return request.user.username

    token = request.COOKIES.get("free_session", "").strip()
    try:
        payload = signing.loads(
            token,
            salt=FREE_SESSION_SALT,
            max_age=FREE_SESSION_MAX_AGE,
        )
    except (BadSignature, SignatureExpired):
        raise ValidationError({"message": "免费访客会话已失效，请重新进入"})

    sid = str(payload.get("sid", "")).strip()
    if len(sid) != 32 or not all(char in "0123456789abcdef" for char in sid):
        raise ValidationError({"message": "免费访客会话无效"})
    return f"{FREE_ACCOUNT_USERNAME}:{sid}"

def req_gateway(method, uri, *args, **kwargs):
    url = CHATGPT_GATEWAY_URL + uri
    headers = {
        "Authorization": "Bearer {}".format(GATEWAY_ADMIN_SECRET),
    }
    try:
        res = requests.request(method, url, headers=headers, *args, **kwargs, allow_redirects=False)
    except RequestException as e:
        raise ValidationError("请求异常, 网关服务未正常启用")

    if res.status_code != 200:
        try:
            err_msg = res.json()
        except:
            err_msg = res.text

        raise ValidationError(err_msg)

    return res.json()


def clean_int_list(data_list):
    if isinstance(data_list, str):
        data_list = json.loads(data_list)

    new_list = []
    for i in data_list:
        if isinstance(i, int):
            new_list.append(i)
        elif isinstance(i, str) and i.isdigit():
            new_list.append(int(i))

    return new_list


def save_visit_log(request, log_type, chatgpt_username=None):

    VisitLog.save_data({
        "ip": get_client_ip(request),
        "log_type": log_type,
        "chatgpt_username": chatgpt_username,
        "username": request.user.username,
        "created_at": int(time.time()),
        "user_agent": request.headers.get('User-Agent'),
    })
