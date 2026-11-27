"""Reserve historical usernames until ownership is migrated to immutable IDs."""
from rest_framework.exceptions import ValidationError
from app.accounts.models import RetiredUsername
from app.utils import req_gateway


def ensure_username_available(name):
    if RetiredUsername.objects.filter(name=name.strip().casefold()).exists():
        raise ValidationError({'username':'该用户名已被历史账号使用，请选择其他用户名'})
    result=req_gateway('post','/api/user-subject-available',timeout=(1,2),json={'user_name':name})
    if not isinstance(result,dict) or result.get('available') is not True:
        raise ValidationError({'username':'该用户名关联历史资源或暂时无法核验，请选择其他用户名或稍后重试'})
