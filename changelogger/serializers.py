from django.conf import settings

from rest_framework import serializers

from .models import ChangeLog

import logging
logger = logging.getLogger(__name__)



class BasicUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.CharField()
    is_staff = serializers.BooleanField()


class ChangeLogSerializer(serializers.Serializer):
    """ Can't use a ModelSerializer because ChangeLog is an abstract base class """
    date_created = serializers.DateTimeField()
    obj_id = serializers.IntegerField()
    obj_content_type = serializers.CharField()
    type = serializers.CharField()
    changes = serializers.JSONField()
    is_m2m = serializers.BooleanField()
    user = BasicUserSerializer()



class ChangeLogListSerializer(serializers.Serializer):
    change_logs = ChangeLogSerializer(many=True, read_only=True)



class ChangeLoggerSerializerMixin(object):
    limit_to_is_staff = False

    @property
    def data(self):
        # Call the super class first
        ret = super(ChangeLoggerSerializerMixin, self).data


        try:
            # TODO: Only return ChangeLogs when additional param is included
            #   e.g. ?change_logs=1


            # Restrict access to GET + is_staff
            request = self._context.get("request")
            logger.debug("limit_to_is_staff: %s" % self.limit_to_is_staff)

            logger.debug("request.user.is_staff: %s" % request.user.is_staff)
            if request.method != 'GET':
                return ret

            if self.limit_to_is_staff and (not request.user.is_authenticated() or not request.user.is_staff):
                return ret

            if hasattr(self.instance, 'full_change_logs'):
                change_logs = self.instance.full_change_logs
            else:
                # This obj isn't being ChangeLogged
                return ret

            serializer = ChangeLogListSerializer({ 'change_logs': change_logs })
            ret.update(serializer.data)
        except Exception as e:
            logger.error(e)

        return ret


class ChangeLoggerStaffOnlySerializerMixin(ChangeLoggerSerializerMixin):
    limit_to_is_staff = True


