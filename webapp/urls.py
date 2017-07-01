#!/usr/bin/python
# -*- coding: UTF-8 -*-
#
# Create your views here.

from django.conf.urls import patterns, include, url

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    url(r'^login/$', 'django.contrib.auth.views.login'),
    url(r'^accounts/login/$', 'django.contrib.auth.views.login'),
    url(r'^logout/$', 'django.contrib.auth.views.logout_then_login'),

    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),

    url(r'^$', 'doctor.views.showIndex'),
    url(r'^loadDrugs/$', 'doctor.views.loadDrugs'),
    url(r'^loadOther/$', 'doctor.views.loadOther'),
    url(r'^exportCsv/$', 'doctor.views.exportCsv'),
    url(r'^exportQueryCsv/(?P<queryId>.+)$', 'doctor.views.exportCsvQuery'),
    url(r'^exportAH/$', 'doctor.views.exportAH'),
    url(r'^showQuery/(?P<queryId>.+)$', 'doctor.views.showQuery'),
    url(r'^doctor/(?P<doctorId>\d+)/add/$', 'doctor.views.addPatient'),
    url(r'^doctor/(?P<doctorId>\d+)$', 'doctor.views.showDoctor'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)$', 'doctor.views.showPatient'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/delete.html$', 'doctor.views.deletePatient'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/add/$', 'doctor.views.addEntry'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/(?P<entryId>\d+)/drug_search$', 'doctor.views.editEntry'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/(?P<entryId>\d+)/drug_check$', 'doctor.views.editEntry'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/(?P<entryId>\d+)/dose_check$', 'doctor.views.editEntry'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/(?P<entryId>\d+)/diseaseChecked$', 'doctor.views.editEntry'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/(?P<entryId>\d+)/$', 'doctor.views.editEntry'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/(?P<entryId>\d+)/entrydone.html$', 'doctor.views.doneEntry'),
    url(r'^doctor/(?P<doctorId>\d+)/(?P<patientId>\d+)/(?P<entryId>\d+)/delete.html$', 'doctor.views.deleteEntry'),
    # url(r'^webapp/', include('webapp.foo.urls')),
    
    # internationalization
    url(r'^i18n/', include('django.conf.urls.i18n')),
    
)
