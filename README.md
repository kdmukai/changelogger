# ChangeLogger #
The ChangeLogger provides per-field change logging for any Django model.


## Integration ##
Here's a simple Django model:

```python
class MyModel(models.Model):
	favorite_color = models.CharField(max_length=128)
	favorite_number = models.IntegerField()
	favorite_foods = models.ManyToManyField('someapp.Food')
```

Next we define a trivial ChangeLog implementation class and add ChangeLoggerModelMixin to our model:

```python
from changelogger.models import ChangeLog, ChangeLogTracker, ChangeLoggerModelMixin
	
class MyModelChangeLog(ChangeLog):
	pass

class MyModel(ChangeLoggerModelMixin, models.Model):
	favorite_color = models.CharField(max_length=128)
	favorite_number = models.IntegerField()
	
	# Configure the ChangeLogger
	change_logger = ChangeLogTracker(
		fields          = ['favorite_color', 'favorite_number',],
		m2ms            = ['favorite_foods'],
		changelog_class = MyModelChangeLog
	)
```
We explicitly define the fields that we want to track when initializing the ChangeLogTracker. Notice that we can also track ManyToManyField changes (m2ms), but more on this below.

change\_log\_class needs to point to a ChangeLog implementation class so that the mix-in will know where to write the log entries. You don't have to have a dedicated ChangeLog implementation class for each model that you're logging. You could have all models write to the same ChangeLog implementation class. For example, if you have a bunch of related business objects (Interview, Appointment, AppointmentTimeSlot) you'll probably want them all writing to the same ChangeLog implementation class so you can extract logs for all related changes in order.

Remember to run:
```
./manage.py makemigrations [appname]
./manage.py migrate [appname]
```
This will add the MyModelChangeLog table to your database.


## Middleware ##
The ChangeLogTracker can include information about who made each change if you also install the changelogger.middleware.ChangeLoggerMiddleware:

```python
MIDDLEWARE_CLASSES = (
	# ...
	'changelogger.middleware.ChangeLoggerMiddleware',
)
```


## Usage ##
There is no impact on your client code. Instantiate objects, update, delete them as usual. The ChangeLogTracker will transparently work behind the scenes.

```python
mymodel = MyModel.objects.get(pk=5)
mymodel.favorite_color = 'purple'
mymodel.favorite_number = 7
mymodel.save()

mymodel.favorite_foods.add(Food.objects.get(name='sushi'))
```


### Output ###
You'll see one new MyModelChangeLog entry:

```
obj_id: 5
obj_content_type: 'mymodel'
type: ChangeLog.TYPE__UPDATE
changes: [
	{
		'field': 'favorite_color',
		'old': 'blue',
		'new': 'purple'
	},
	{
		'field': 'favorite_number',
		'old': 5,
		'new': 7
	},
]
is_m2m: False
```

And obviously the ChangeLog will only log the fields that have changed. Unchanged fields are ignored and won't appear in the log.


## ManyToManyField changes ##
The m2m change in the example above would be logged separately:

```
obj_id: 5
obj_content_type: 'mymodel'
type: ChangeLog.UPDATE
changes: [
	{
		'field': 'favorite_foods',
		'old': None,
		'new': [23, 41, 7]
	}
]
is_m2m: True
```

We do not track the original state of m2m fields. The logger only notes the updated m2m id list after a change has been made.


## Other Operations ##
`ChangeLog.TYPE__CREATE`: When creating objects the `old` json field will be `None` and the value of all tracked fields will be logged.

`ChangeLog.TYPE__DELETE`: On delete, all tracked fields will be logged in the `old` json field while `new` will be `None`.


## Serializer ##
There is also an experimental Serializer to include an object's ChangeLog when it is requested from a Django REST API call.

Work here is ongoing.


### Acknowledgments ###
The ChangeLoggerMixin was adapted from Armin's original suggestion at: http://stackoverflow.com/a/111364/1639020
