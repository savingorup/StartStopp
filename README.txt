Running server (on websrv):

screen
set DJANGO_SETTINGS_MODULE=webapp.settings
python2 manage.py runserver 0.0.0.0:17171
manage.bat runserver 0.0.0.0:17171


Initial south migration:


Changes in models:

set DJANGO_SETTINGS_MODULE=webapp.settings
python manage.py schemamigration doctor --auto
python manage.py migrate doctor

Migrate to production server

python2 manage.py syncdb

python2 manage.py migrate doctor --fake 0001
(this is the number of LAST PREVIOUS MIGRATION - then one with last number on server!)
(copy all new migrations from doctor/migrations dir!)
python2 manage.py migrate
(this syncs migrations!)

LOCALIZATION

Update translations:

set DJANGO_SETTINGS_MODULE=webapp.settings
python manage.py makemessages -a

Edit ..\StartStopp\app\locale\sl\LC_MESSAGES\django.po

manage.bat compilemessages

creates django.mo

