import threading

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db import models
from django.db.models.signals import m2m_changed
from django.utils.encoding import smart_str

from django_extensions.db.fields import CreationDateTimeField
from jsonfield import JSONField

import logging
logger = logging.getLogger(__name__)



"""--------------------------------------------------------------------
	Abstract 
--------------------------------------------------------------------"""
class ChangeLog(models.Model):
	TYPE__CREATE	= 'CREATE'
	TYPE__UPDATE	= 'UPDATE'
	TYPE__DELETE	= 'DELETE'
	TypeChoices = (
		(TYPE__CREATE, "Create"),
		(TYPE__UPDATE, "Update"),
		(TYPE__DELETE, "Delete"),
	)

	obj_id              = models.IntegerField(null=True)
	obj_content_type 	= models.ForeignKey(ContentType, related_name="%(app_label)s_%(class)s_obj_content_type", null=True)
	object_instance     = GenericForeignKey('obj_content_type', 'obj_id')
	
	date_created        = CreationDateTimeField()
	user                = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True)
	type 				= models.CharField(max_length=10, choices=TypeChoices, default=TYPE__UPDATE)
	changes       		= JSONField(blank=True, null=True)
	is_m2m				= models.BooleanField(default=False)
	
	class Meta:
		abstract = True
		ordering = ('-pk',)

	def __unicode__(self):
		return "%i: %s %i %s" % (self.id, self.obj_content_type, self.obj_id, self.type)



class ChangeLogTracker(object):
	# Must specify threading for middleware access
	thread = threading.local()

	def __init__(self, *args, **kwargs):
		self._fields = kwargs.pop('fields', None)
		self._m2ms = kwargs.pop('m2ms', None)
		self._changelog_class = kwargs.pop('changelog_class', None)

	@property
	def fields(self):
		return self._fields

	@property
	def m2ms(self):
		return self._m2ms

	@property
	def changelog_class(self):
		return self._changelog_class



"""--------------------------------------------------------------------
	Modified from:
	http://stackoverflow.com/a/111364/1639020
--------------------------------------------------------------------"""
class ChangeLoggerModelMixin(object):

	@property
	def change_logs(self):
		""" Returns the full ChangeLog for this instance """
		# Must specify obj_content_type since different types can write to the same ChangeLog
		obj_content_type = ContentType.objects.get_for_model(self)
		return self.change_logger.changelog_class.objects.filter(obj_id=self.id, obj_content_type=obj_content_type)


	@property
	def full_change_logs(self):
		""" Implement in the child class, otherwise just returns its own logs """
		return self.change_logs


	def __init__(self, *args, **kwargs):
		# Must call parent __init__ first to populate initial values!!
		super(ChangeLoggerModelMixin, self).__init__(*args, **kwargs)

		try:
			# content_type is used for Exceptions below
			content_type = ContentType.objects.get_for_model(self)

			# Check for required config in the child class
			if not hasattr(self, 'change_logger'):
				raise Exception('ChangeLoggerModelMixin: change_logger=ChangeLogTracker(fields, changelog_class) was not defined in the child class %s.%s' % (content_type.app_label, content_type.model))

			if not self.change_logger.fields:
				raise Exception('ChangeLoggerModelMixin: change_logger_config["fields"] was not defined in the child class %s.%s' % (content_type.app_label, content_type.model))

			if not self.change_logger.changelog_class:
				raise Exception('ChangeLoggerModelMixin: change_logger_config["changelog_class"] was not defined in the child class %s.%s' % (content_type.app_label, content_type.model))

			# Is this update or create?
			if self.pk:
				# Save the obj's state for later diffs.
				self._original_state = dict(self.__dict__)
				logger.debug("init existing %s.%s" % (self.__class__.__module__, self.__class__.__name__))

				# Wire up each m2m 'changed' signal
				if self.change_logger.m2ms:
					for m2m in self.change_logger.m2ms:
						# Note we do NOT save the original m2m value because it is not accessible in
						#	the m2m_changed signal; the instance we get in the signal already has 
						#	the new m2ms in it.
						# Specify a dispatch_uid to guarantee that this only gets bound once
						dispatch_uid = "ChangeLogger|%s.%s_%s" % (self.__class__.__module__, self.__class__.__name__, m2m)
						logger.debug("Wiring m2m_changed: %s" % dispatch_uid)
						m2m_changed.connect(self.handle_m2m_changed_signal, sender=getattr(type(self), m2m).through, dispatch_uid=dispatch_uid)
			else:
				logger.debug("init NEW %s.%s" % (self.__class__.__module__, self.__class__.__name__))

		except Exception as e:
			logger.error(e)


	def save(self, *args, **kwargs):
		# Save first, just in case anything goes wrong during logging...
		super(ChangeLoggerModelMixin, self).save(*args, **kwargs)

		# Encapsulate everything in try/except to insulate Model from bad effects
		try:
			# Each field change will be stored as its own JSON entry in this array
			changes_json = []

			# Is this update or create?
			if not hasattr(self, '_original_state') or not self._original_state:
				# On CREATE we log *all* fields on the list.
				logger.debug("CREATE")
				type = ChangeLog.TYPE__CREATE
				changes_json = self._log_all_fields()

			else:
				# On UPDATE we only log the fields on the list that have changed.
				logger.debug("UPDATE")
				type = ChangeLog.TYPE__UPDATE

				for field in self.change_logger.fields:
					orig_value = self._original_state.get(field, None)
					if orig_value:
						# Convert all values to a valid string
						orig_value = smart_str(orig_value)
					new_value  = self.__dict__.get(field, None)
					if new_value:
						# Convert all values to a valid string
						new_value = smart_str(new_value)
					if orig_value != new_value:
						changes_json.append(
							self._new_change_entry(
								field=field,
								old=orig_value,
								new=new_value
							)
						)

			# Create the new log entry
			if len(changes_json) > 0:
				self._create_change_log(type=type, changes_json=changes_json)

				# Update '_original_state' so we can track further changes on this instance
				self._original_state = dict(self.__dict__)

			else:
				# No changes to log.
				#### ---  debugging --- ####
				obj_content_type = ContentType.objects.get_for_model(self)
				logger.debug("No changes to log for %s.%s" % (obj_content_type.app_label, obj_content_type.model))
				#### --- /debugging --- ####
				pass

		except Exception as e:
			# Catch the Exception and log it, but carry on so the core code remains unaffected
			#	by the ChangeLogger's problems.
			logger.error(e)


	def delete(self, *args, **kwargs):
		# Encapsulate everything in try/except to insulate Model from bad effects
		try:
			# On delete log *all* fields since we will no longer have a record of this obj in the DB
			changes_json = self._log_all_fields()
			self._create_change_log(type=ChangeLog.TYPE__DELETE, changes_json=changes_json)
		except Exception as e:
			# Catch the Exception and log it, but carry on so the core code remains unaffected
			#	by the ChangeLogger's problems.
			logger.error(e)

		# Have to delete at the *end* to preserve the obj id
		super(ChangeLoggerModelMixin, self).delete(*args, **kwargs)



	@staticmethod	# Must be a static method so the signal dispatcher can invoke it.
	def handle_m2m_changed_signal(sender, **kwargs):
		""" We can only track the *current* state of m2m fields. So on each m2m add/clear/remove
				we simply store the full m2m id list. """
		try:
			if kwargs['action'] not in ('post_add', 'post_clear', 'post_remove'):
				return

			# 'instance' will be the child implementation class.
			instance = kwargs['instance']
			logger.debug("m2m_changed: %s.%s %i" % (instance.__class__.__module__, instance.__class__.__name__, instance.pk))
			logger.debug("sender: %s" % sender)

			# 'sender' is a class. e.g. <class 'foo.bar.models.Bar_somem2mfield'>
			#	Extract __name__ ('Bar_m2mfield') and split on underscore: ['Bar', 'somem2mfield']
			#	The second item will be the m2m field name that has changed: 'somem2mfield'
			m2m = sender.__name__.split('_', 1)[1]
			logger.debug("logging '%s' m2m" % m2m)

			# Call the many-to-many relation's "all()" method and list the linked ids.
			#	Equivalent to calling: mybar.somem2mfield.all()
			new_value  = smart_str( getattr(getattr(instance, m2m), 'all')().values_list('id') )

			change_json = instance._new_change_entry(
				field=m2m,
				new=new_value
			)

			# Only a single change goes into this changes_json
			changes_json = [(change_json)]

			instance._create_change_log(type=ChangeLog.TYPE__UPDATE, changes_json=changes_json, is_m2m=True)
		except Exception as e:
			logger.error(e)


	def _new_change_entry(self, field, old=None, new=None):
		""" Internal convenience method to generate consistently-formatted JSON log entries """
		return {
			'field': field,
			'old': old,
			'new': new,
		}


	def _log_all_fields(self):
		""" Writes the current value of *all* fields on the list """
		changes_json = []
		for field in self.change_logger.fields:
			new_value = self.__dict__.get(field, None)
			changes_json.append(
				self._new_change_entry(
					field=field,
					new=smart_str(new_value)
				)
			)
		return changes_json


	def _create_change_log(self, type, changes_json, is_m2m=False):
		""" Saves the changes_json to the target ChangeLog table """
		obj_id = self.id
		obj_content_type = ContentType.objects.get_for_model(self)

		# Try to extract the User (requires ChangeLoggerMiddleware)
		user = None
		if hasattr(ChangeLogTracker.thread, 'request'):
			try:
				user = ChangeLogTracker.thread.request.user
			except Exception as e:
				logger.error(e)

		logger.debug("user: %s" % user)
		logger.debug("obj_id: %i" % obj_id)
		logger.debug("obj_content_type: %s.%s" % (obj_content_type.app_label, obj_content_type.model))
		logger.debug(changes_json)

		self.change_logger.changelog_class.objects.create(
			user=user, 
			obj_id=obj_id,
			obj_content_type=obj_content_type,
			type=type,
			is_m2m=is_m2m,
			changes=changes_json
		)



