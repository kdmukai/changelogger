from django.contrib import admin


class ChangeLogAdmin(admin.ModelAdmin):
	list_display = ('date_created',	'obj_content_type', 'obj_id', 'field_name', 'original_value', 'updated_value',)
	list_filter = ('date_created', 'obj_content_type', 'obj_id',)
