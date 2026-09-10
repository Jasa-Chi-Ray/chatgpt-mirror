from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from app.accounts.models import User
from app.chatgpt.models import ChatgptCar
from app.chatgpt.serializers import ShowGptCarSerializer, AddChatgptCarModelSerializer, DeleteChatgptCarSerializer
from app.page import DefaultPageNumberPagination
from app.utils import clean_int_list


class GptCarEnum(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request):
        result = ChatgptCar.objects.order_by("-id").values("id", "car_name").all()
        return Response({"data": result})


class GptCarView(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated, IsAdminUser)
    queryset = ChatgptCar.objects.order_by("-id").all()
    serializer_class = ShowGptCarSerializer
    pagination_class = DefaultPageNumberPagination

    def post(self, request, *args, **kwargs):
        obj = ChatgptCar.objects.filter(id=request.data.get("id")).first()
        serializer = AddChatgptCarModelSerializer(instance=obj, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, *args, **kwargs):
        serializer = DeleteChatgptCarSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ChatgptCar.objects.filter(id__in=serializer.data["ids"]).delete()
        return Response({"message": "删除成功"})


class GptCarDetailView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    def get(self, request, car_id):
        car = ChatgptCar.objects.filter(id=car_id).first()
        if not car:
            return Response({"message": "号池不存在"}, status=404)

        assigned_users = []
        available_users = []
        users = (
            User.objects.filter(is_superuser=False)
            .order_by("username")
            .values("id", "username", "is_active", "expired_date", "gptcar_list")
        )
        for user in users:
            item = {
                "id": user["id"],
                "username": user["username"],
                "is_active": user["is_active"],
                "expired_date": user["expired_date"],
            }
            target = assigned_users if car.id in clean_int_list(user["gptcar_list"] or []) else available_users
            target.append(item)

        return Response({
            "id": car.id,
            "car_name": car.car_name,
            "remark": car.remark,
            "assigned_users": assigned_users,
            "available_users": available_users,
        })


class GptCarUserAssignmentView(APIView):
    permission_classes = (IsAuthenticated, IsAdminUser)

    @staticmethod
    def _get_car_and_users(car_id, request):
        car = ChatgptCar.objects.filter(id=car_id).first()
        if not car:
            raise ValidationError({"message": "号池不存在"})

        raw_user_ids = request.data.get("user_ids")
        if not isinstance(raw_user_ids, list) or not raw_user_ids:
            raise ValidationError({"user_ids": "请选择用户"})

        parsed_user_ids = clean_int_list(raw_user_ids)
        if len(parsed_user_ids) != len(raw_user_ids) or any(isinstance(item, bool) for item in raw_user_ids):
            raise ValidationError({"user_ids": "用户列表格式错误"})
        user_ids = list(dict.fromkeys(parsed_user_ids))

        users = list(User.objects.filter(id__in=user_ids, is_superuser=False))
        if len(users) != len(user_ids):
            raise ValidationError({"user_ids": "部分用户不存在或不可操作"})
        return car, users

    def post(self, request, car_id):
        car, users = self._get_car_and_users(car_id, request)
        changed_users = []
        for user in users:
            car_ids = clean_int_list(user.gptcar_list or [])
            if car.id not in car_ids:
                user.gptcar_list = [*car_ids, car.id]
                changed_users.append(user)
        if changed_users:
            for user in changed_users:
                user.save(update_fields=["gptcar_list"])
        return Response({"message": "用户已加入号池"})

    def delete(self, request, car_id):
        car, users = self._get_car_and_users(car_id, request)
        changed_users = []
        for user in users:
            car_ids = clean_int_list(user.gptcar_list or [])
            new_car_ids = [item for item in car_ids if item != car.id]
            if new_car_ids != car_ids:
                user.gptcar_list = new_car_ids
                changed_users.append(user)
        if changed_users:
            for user in changed_users:
                user.save(update_fields=["gptcar_list"])
        return Response({"message": "用户已移出号池"})
