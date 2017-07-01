#!/usr/bin/python
# -*- coding: UTF-8 -*-

# this model uses South for DB migrations
# after changes in model do:
# set DJANGO_SETTINGS_MODULE=webapp.settings
# python manage.py schemamigration doctor --auto
# python manage.py migrate doctor
# DON'T FORGET - in production server it may be 
# $ /usr/bin/python2 ...
# 

from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy, get_language

# all models which do not define primary key have automatic "id" field!

# Doctor: linked to User
class Doctor (models.Model):
    # link to users!
    user = models.OneToOneField(User)
    rand_block = models.CharField (max_length=24, default='')
    def __unicode__(self):
        return unicode(self.user)

# Patient. A doctor has multiple patients.
class Patient (models.Model):
    first_name = models.CharField (max_length=200, verbose_name=ugettext_lazy('First Name'))
    last_name = models.CharField (max_length=200, verbose_name= ugettext_lazy('Family Name'))
    year_of_birth = models.PositiveIntegerField ()
    GENDER_CHOICES = (
        ('M', ugettext_lazy('Male')),   # 'Moški' 'Ženska'
        ('F', ugettext_lazy('Female')),
    )
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    doctor = models.ForeignKey(Doctor)
    STATUS_CHOICES = (
        ('E', 'Undecided'),
        ('I', 'Inactive'),
        ('C', 'Control group'),
        ('R', 'Research group'),
        ('N', 'Not in research'),
    )
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default='E')
    contact = models.CharField (max_length=120, null=True)
    def __unicode__(self):
        return u"%s %s" % (self.first_name, self.last_name)
    class Meta:
        ordering=('last_name',)
        verbose_name = ugettext_lazy('Patient')
        verbose_name_plural = ugettext_lazy('Patients')

# a single entry. One patient can have multiple entries.       
class Entry (models.Model):
    dt = models.DateTimeField()
    other_diseases = models.TextField(max_length=1024, null=True)
    patient = models.ForeignKey(Patient)
    class Meta:
        ordering=('dt',)

# Diseases. N:N to Entry
class Disease (models.Model):
    code = models.CharField(max_length=8, primary_key=True)
    group_en = models.CharField(max_length=128)
    group_si = models.CharField(max_length=128)    
    description_en = models.CharField(max_length=128)
    description_si = models.CharField(max_length=128)
    displaycode = models.CharField(max_length=10, default="ERR")
    entries = models.ManyToManyField(Entry)
    def getGroup (self):
        return self.group_si if "sl" in get_language() else self.group_en
    def getDescription (self):
        return self.description_si if "sl" in get_language() else self.description_en
    def __unicode__ (self):
        return u"%s %s" % (self.code, self.getDescription())
    class Meta:
        ordering=('code',)

# Questions. N:N to Entry        
class Question (models.Model):
    code = models.CharField(max_length=8, primary_key=True)
    description_en = models.CharField (max_length=200)
    description_si = models.CharField (max_length=200)
    entries = models.ManyToManyField(Entry)
    def getDescription (self):
        return self.description_si if "sl" in get_language() else self.description_en
    def __unicode__ (self):
        return u"%s %s" % (self.code, self.getDescription())
    class Meta:
        ordering=('code',)

# Criterias. N:N to Entry
class Criteria (models.Model):
    code = models.CharField(max_length=8, primary_key=True)
    if_clause = models.CharField (max_length=1000)
    description_en = models.CharField (max_length=1000)
    description_si = models.CharField (max_length=1000)
    versions = models.CharField (max_length=32, default="A")
    entries = models.ManyToManyField(Entry)
    def getDescription (self):
        return self.description_si if "sl" in get_language() else self.description_en
    def __unicode__ (self):
        return u"%s %s" % (self.code, self.getDescription())
    class Meta:
        ordering=('code',)

# Drug groups. 1:N to Drugs
class DrugGroup (models.Model):
    name = models.CharField (max_length=40, primary_key=True)
    column = models.CharField (max_length=8, default="O")
    keywords = models.CharField (max_length=200, default="")    

# Drugs. N:N to Entry, but with additional data. Also N:N to DrugGroups
class Drug (models.Model):
    code = models.PositiveIntegerField(primary_key=True)
    name = models.CharField (max_length=250)
    unit = models.CharField (max_length=64)
    doseperunit = models.FloatField (default=0.0)
    atc = models.CharField (max_length=8)
    substances = models.CharField (max_length=250)    
    groups = models.ManyToManyField(DrugGroup)    
    entries = models.ManyToManyField(Entry, through='DrugEntry')
    def __unicode__ (self):
        return u"%s %s" % (self.code, self.name)
    class Meta:
        ordering=('name',)
    
class DrugEntry (models.Model):
    entry = models.ForeignKey(Entry)
    drug = models.ForeignKey(Drug)
    dose_amount = models.FloatField()
    DOSETIME_CHOICES = (
        ('D', ugettext_lazy('per day') ), # 'na dan' 'na teden' 'na mesec'
        ('T', ugettext_lazy('per week') ),
        ('M', ugettext_lazy('per month') ),
    )
    dose_time = models.CharField(max_length=1, choices=DOSETIME_CHOICES)    
    PATIENTKNOWS_CHOICES = (
        ('Y', ugettext_lazy('Yes') ), # 'Da' 'Ne'
        ('N', ugettext_lazy('No') ),
    )
    patient_knows = models.CharField(max_length=1, choices=PATIENTKNOWS_CHOICES, default='N')
    def __unicode__ (self):
        return u"%s %s" % (self.entry, self.drug)
