#!/usr/bin/python
# -*- coding: UTF-8 -*-

from django.contrib import admin
from models import Doctor, Patient, Disease, Question, Criteria, Drug

admin.site.register(Doctor)
admin.site.register(Patient)
admin.site.register(Disease)
admin.site.register(Question)
admin.site.register(Criteria)
admin.site.register(Drug)