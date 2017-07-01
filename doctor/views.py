#!/usr/bin/python
# -*- coding: UTF-8 -*-
#

import logging, csv, json, ast, os
import operator, re, random
from datetime import datetime, date
import urllib2
import uuid, tempfile

from django.template import RequestContext
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response, redirect
#from django.utils import simplejson
#from django.utils.translation import ugettext as _
#from django.template.loader import render_to_string
from django import forms
from django.utils.timezone import utc
from django.utils.translation import ugettext as _
#from django.utils.translation import get_language
from django.utils.html import escape

from models import *

################################################################################
#                           MODULE LOGGING
################################################################################

log=logging.getLogger("startstopp")

################################################################################
#                     AST TREE PARSING & CALCULATION
################################################################################

class AstNodeVisitor (ast.NodeVisitor):
    """ a simple AST visitor. Just gathers (variable) names in a list """
    def __init__ (self):
        self.names=[]
    def visit_Name(self, node): 
        #print 'Name:', node.id
        if not node.id in self.names:
            self.names.append(node.id)
    def generic_visit(self, node):
        #print type(node).__name__
        ast.NodeVisitor.generic_visit(self,node)

class AstBoolEvaluator:
    """ can evaluate AST tree with boolean, comparator, binary expressions """
    def __init__ (self):
        self.MODE_EVALUATE=1
        self.MODE_COLLECT_UNDEFINED=2
        self.operators = { 
            ast.And: operator.__and__, 
            ast.Or: operator.__or__, 
            ast.Not: operator.__not__,
            ast.Eq: operator.__eq__, 
            ast.Lt: operator.__lt__, ast.LtE: operator.__le__,
            ast.Gt: operator.__gt__, ast.GtE: operator.__ge__,
            ast.Add: operator.__add__,
        }
        self.variables={ }
        self.mode=self.MODE_EVALUATE
        self.undefined=[]
        self.shortEvaluation=False
        
    def collectUndefined (self, expr, known_variables={}):
        """ returns 2 sets of variables: one as short-circuit evaluation and one as full """
        #print "EXPR:", expr
        self.shortEvaluation=False
        self.eval_expr(expr, known_variables, self.MODE_COLLECT_UNDEFINED)
        set1=self.undefined
        self.shortEvaluation=True
        self.eval_expr(expr, known_variables, self.MODE_COLLECT_UNDEFINED)
        set2=self.undefined
        #print "UNDEF:::", set1, set2
        return (set1, set2)        
    
    def evaluate (self, expr, variables={}):
        return self.eval_expr(expr, variables, self.MODE_EVALUATE) 

    def eval_expr (self, expr, variables={}, mode=None):
        """ expr is a string: 'A<5 or B>3' """
        if mode is None:
            self.mode=self.MODE_EVALUATE
        else:
            self.mode=mode
        self.variables=variables
        #print(variables)
        self.undefined=[]
        tree=ast.parse(expr)
        #print "EXPR:", ast.dump(tree)
        return self.eval_(tree.body[0].value) # Module(body=[Expr(value=...)])
        
    def op2func (self, astOp):
        """ may throw KeyError if node.op is not in operators """
        return self.operators[astOp.__class__]
        
    def eval_(self, node):
        #print "NODE ", node
        if isinstance(node, ast.Num): # <number>/constant
            return node.n    
        elif isinstance(node, ast.BoolOp): # <left> <operator> <right>
            val=self.eval_(node.values[0])            
            if self.shortEvaluation:                
                #print "BOOLOP short lval=", val
                # short-circuit evaluation!
                is_and = isinstance(node.op, ast.And)
                if (is_and and val) or (not is_and and not val):
                    for n in node.values:
                        val = self.op2func(node.op)(val, self.eval_(n))
                        # short-circuit evaluation!
                        if (is_and and not val) or (not is_and and val):
                            break
            else:
                # full expression evaluation!
                #print "BOOLOP long lval=", val
                for n in node.values:
                    val = self.op2func(node.op)(val, self.eval_(n))
            #print "BOOLOP ret=val"
            return val
        elif isinstance(node, ast.Compare): # <left> <operator> <right>
            #print "COMPARE "
            lval=self.eval_(node.left)
            #print "COMPARE LVAL=", lval
            out=True
            for op, rnode in zip(node.ops,node.comparators):
                rval=self.eval_(rnode)
                #print "COMPARE RVAL=", rval
                out=self.op2func(op)(lval, rval)
                #print "COMPARE TMP RESULT:", out
                lval=rval       # syntax a<b<c!!!
                if not out:
                    break
            #print "COMPARE DONE :", out
            return out    
        elif isinstance(node, ast.BinOp): # <left> <operator> <right>
            #print "BINOP "
            lval=self.eval_(node.left)
            #print "BINOP LVAL=", lval
            rval=self.eval_(node.right)
            #print "BINOP RVAL=", rval
            out = self.op2func(node.op)(lval, rval)
            #print "BINOP DONE :", out
            return out    
        elif isinstance(node, ast.UnaryOp):
            #print "NOT "
            return self.op2func(node.op)( self.eval_(node.operand) )
        elif isinstance(node, ast.Name):
            if (node.id == "True"): return True
            if (node.id == "False"): return False
            if (node.id in self.variables):
                #print "VAR ", node.id, "=", self.variables[node.id]
                return self.variables[node.id]
            if self.mode==self.MODE_COLLECT_UNDEFINED:
                #print "UNDEF ", node.id
                self.undefined.append(node.id)
                return True
            else:
                log.error("Name %s not found among defined [%s]" % (node.id, str(self.variables)))
                raise NameError(node.id)
        else:
            log.error("NODE %s IS NOT DEFINED" % (str(node,)))
            raise TypeError(node)


################################################################################
#                          UNICODE CSV READER
################################################################################

class UnicodeCsvReader(object):
    def __init__(self, f, encoding="utf-8", **kwargs):
        self.csv_reader = csv.reader(f, **kwargs)
        self.encoding = encoding

    def __iter__(self):
        return self

    def next(self):
        # read and split the csv row into fields
        row = self.csv_reader.next() 
        # now decode
        return [unicode(cell, self.encoding) for cell in row]

    @property
    def line_num(self):
        return self.csv_reader.line_num


################################################################################
#                               GLOBALS
################################################################################

class ViewGlobalsClass:
    def __init__ (self):
        self.drugsAutocompleteCorpus=None
        self.diseasesGroups=None
        self.drugGroups=None
        self.diseasesGroupsLang=None
        self.antiholinergics=None
        
    def createOrAdd (self, d, key, val, maxLen):
        if key in d:
            if len(d[key]) > maxLen:
                return
            if not val in d:
                d[key].append(val)
        else:
            d[key]=[ val ]
    
    def buildDrugAutocompleteCache (self):
        if self.drugsAutocompleteCorpus:
            return
        log.info("Building drug autocomplete cache...")
        drugs=Drug.objects.all()
        maxMatch=50
        self.drugsAutocompleteCorpus={}
        for d in drugs:
            for letters in range(2,18):
                if len(d.name) < letters:
                    break
                subs=d.name[:letters].upper()
                self.createOrAdd(self.drugsAutocompleteCorpus, subs, d.name, maxMatch)
        log.info("Drug autocomplete cache %d entries" % (len(self.drugsAutocompleteCorpus,)))
        #for key,val in self.drugsAutocompleteCorpus.iteritems():
        #    print key, "---->", val
        #    print "------------------------------------------------------------"
        # print self.drugAutocomplete("SEVREDO")
        
    def drugAutocomplete (self, s):
        if s in self.drugsAutocompleteCorpus:
            return self.drugsAutocompleteCorpus[s]  # (full name)
    def isDrug (self, drugName):
        try:
            nmdrg=drugName.strip()
            drug=Drug.objects.filter(name=nmdrg)[0]
            log.info("Entered drug ok: %s" % (drugName,))
            return True
        except:
            log.warning("Entered drug not found: %s" % (drugName,))
            return False                    

    def getDiseasesGroups (self):
        # if user changed language, we need to rebuild the cache
        if self.diseasesGroupsLang==get_language():
            if not self.diseasesGroups is None:
                return self.diseasesGroups  # cached
        self.diseasesGroupsLang=get_language()
        # rebuild diseases list by groups
        diseases=Disease.objects.all()
        # create a map of objects. Keys are disesases groups, values are (sorted) list of diseases
        # lists are sorted by group ordering number 
        dgrps={}
        for d in diseases:
            grpOrder=int(d.displaycode.split(".")[0])   # group major
            disOrder=int(d.displaycode.split(".")[1])   # orderding within group
            dgkey=(grpOrder, d.getGroup())
            if not dgkey in dgrps:
                dgrps[dgkey]=[]
                #print dgkey, " reset!"
            dgrps[dgkey].append( (disOrder, {'code':d.code, 'description': d.getDescription()}) )
            #print dgkey, " appended!"
            dgrps[dgkey].sort()  # keep sorted by display order
        #print "GRPS:", dgrps
        #print "--------------------------------------------------------"
        #print "SORTED GRPS:", sorted(dgrps)
        #print "--------------------------------------------------------"
        # use sorted(self.diseasesGroups) to get a list sorted by group display number
        self.diseasesGroups=[]
        for dg in sorted(dgrps):
            self.diseasesGroups.append( [ dg[1], [ x[1] for x in dgrps[dg] ] ] )
        #log.warning("Diseases/groups: %s" % (str(self.diseasesGroups),))
        #print "--------------------------------------------------------"
        return self.diseasesGroups
    
    def getDrugGroups (self):
        if not self.drugGroups is None:
            return self.drugGroups  # cached
        # rebuild drug list by groups
        groups=DrugGroup.objects.all()
        for g in groups:
            drugs=g.drug_set.all()
            self.drugGroups[g.name]=[ drug.code for drug in drugs ]
        #print groups
        return self.drugGroups  # cached
        
    def setDrugGroups (self, groups):
        self.drugGroups=groups
        
    def parseCriterium (self,code,crit, lists):
        log.info("Parsing criteria %s" % (code,))
        s=crit.replace(" OR "," or ").replace(" AND "," and ").replace(" NOT "," not ").replace(".dd","").strip()
        if s.startswith("NOT "):        # condition can start with "not ..." 
            s="not "+s[4:]
        visitor=AstNodeVisitor()
        try:
            parseTree=ast.parse(s)
            visitor.visit(parseTree)
            #print "visited ok, names=", visitor.names            
            for n in visitor.names:
                found=False
                for listName, listEntries in lists.iteritems():
                    #print n.upper(), listName, listEntries[0]
                    if n.upper() in listEntries[0]:
                        lists[listName][1].append(n)
                        #print n,"-- found in --", listName
                        found=True
                if not found:
                    log.error("%s: name %s not found!" % (code, n))
        except:
            log.exception("%s : parsing failure!" % (code,))
            raise
        for listName, listEntries in lists.iteritems():
            if len(listEntries[1])>0:
                log.info("- %s: %s" % (listName, str(listEntries[1])))

    def parseAllCriteria (self):
        for c in Criteria.objects.all():
            # lists is mutable, keep in loop!
            lists={ 
                   "diseases": ( [ d.code for d in Disease.objects.all() ], [] ),
                   "questions": ( [ q.code for q in Question.objects.all() ], [] ),
                   "druggroups": ( [ dg.name for dg in DrugGroup.objects.all() ], [] ),
            }
            self.parseCriterium(c.code,c.if_clause, lists)
            
    def buildKnownVars (self, patient, e):
        variabs={}
        variabs["MALE"]=(patient.gender=="M")
        variabs["FEMALE"]=(patient.gender=="F")
        if (patient.year_of_birth<1900):
            variabs["AGE"]=datetime.now().year - (1900+patient.year_of_birth)
        else:
            variabs["AGE"]=datetime.now().year - patient.year_of_birth
        for d in Disease.objects.all(): 
            variabs[d.code]=False
        for d in e.disease_set.all(): 
            variabs[d.code]=True        
        for d in DrugGroup.objects.all(): 
            variabs[d.name]=0.0
            variabs[d.name+"_count"]=0.0
        fndGroup=False
        for de in DrugEntry.objects.filter(entry=e):
            # for all drugs in entry
            d=de.drug
            for dg in d.groups.all():
                # for all groups in which this drug belongs to
                amount=de.dose_amount
                if d.doseperunit==0.0:
                    dpu=0.00001     # use some minimal value to fulfill >0 conditions!
                else:
                    dpu=d.doseperunit
                dose=amount*dpu
                if de.dose_time=="T": doses=[dose/7, dose, dose*4]
                elif de.dose_time=="M": doses=[dose/30, dose/7, dose]            
                else: doses=[dose, dose*7, dose*30]
                variabs[dg.name+".dd"]=doses[0]
                variabs[dg.name+".td"]=doses[1]
                variabs[dg.name+".md"]=doses[2]
                variabs[dg.name+"_count"]=variabs[dg.name+"_count"]+1.0
                variabs[dg.name]=doses[0]       # simplified = daily dose
                log.info("%s found in group %s daily dose %f mg" % (d.name, dg.name, doses[0]))
                fndGroup=True
        if not fndGroup:
            log.info("%s not found in any group!" % (d.name,))                
        #print "KNOWN VARS==>", variabs
        return variabs
    
    def evaluateDuplicates (self, e):
        usedDrugs=[]
        for de in DrugEntry.objects.filter(entry=e):
            # for all drugs in entry
            d=de.drug
            if len(d.atc)<5:
                log.info("Drug %s ignored in duplicates, ATC code too short!" % (d.name, ))
                continue
            # store first 5 characters of ATC
            log.info("Drug %s ATC code %s" % (d.name, d.atc[:5]))
            usedDrugs.append( [ d.atc[:5], d.name ] )
        # find duplicates
        dups=[]
        for d1_idx in range(len(usedDrugs)):
            d1=usedDrugs[d1_idx]
            dups_d1=[]
            for d2_idx in range(d1_idx+1,len(usedDrugs)) :
                d2=usedDrugs[d2_idx]
                if d1[0]==d2[0]:
                    log.info("Drug %s duplicate found %s" % (d1[1], d2[1]))
                    dups_d1.append(d2[1])
            if len(dups_d1)>0:
                dups.append( [ d1[1] ] + dups_d1 )
        if len(dups)>0:
            log.info("Drug duplicates found: %s" % (str(dups)))
        else:
            log.info("No drug duplicates found")
        return dups
        
            
    def getRequiredQuestions (self, patient, entry):
        abe=AstBoolEvaluator()
        variabs=self.buildKnownVars(patient, entry)
        q=[]
        duplicates=self.evaluateDuplicates(entry)
        #for c in Criteria.objects.filter(code="K2"):
        for c in Criteria.objects.all():
            if c.code=="K64":                
                if len(duplicates)>0:
                    q.append('V29')
                    log.info("Criteria %s (duplicates) met, requesting question V29" % (c.code, ))
                continue
            v=variabs.copy()
            cond=c.if_clause.replace(".dd","").replace(".td","").replace(".md","").replace(".count","_count").replace(" OR "," or ").replace(" AND "," and ").replace(" NOT "," not ").strip()
            if cond.startswith("NOT "):        # condition can start with "not ..." 
                cond="not "+cond[4:]
            set1,set2=abe.collectUndefined(cond, v)
            #print "UNDEFINED==>", set1, set2
            if len(set2)>0:
                log.info("Criteria %s partially met, requesting questions %s" % (c.code, str(set2)))
                q.extend(set2)   # adds all items in set2 to rval
        q=list(set(q))  # make every item in list appear only once. Also sort it along the way :)
        log.info("QUESTIONS::: %s" % (str(q),))
        return (Question.objects.filter(code__in=q), duplicates)
    
    def getBrokenCriteria(self, patient, entry):
        log.info("Evaluating criteria...")
        abe=AstBoolEvaluator()
        variabs=self.buildKnownVars(patient, entry)
        for q in Question.objects.all(): 
            variabs[q.code]=False
        for q in entry.question_set.all(): 
            variabs[q.code]=True        
        active=[]
        for c in Criteria.objects.all():
            #log.info("Evaluating criteria: %s [%s]" % (c.code, c.if_clause))
            v=variabs.copy()
            cond=c.if_clause.replace(".dd","").replace(".count","_count").replace(".td","").replace(".md","").replace(" OR "," or ").replace(" AND "," and ").replace(" NOT "," not ").strip()
            if cond.startswith("NOT "):        # condition can start with "not ..." 
                cond="not "+cond[4:]
            val=abe.evaluate(cond, v)
            if val:
                log.info("Criteria %s ACTIVE!" % (c.code,))
                active.append(c.code)
        return active
    
    def matchesQuery(self, patient, entry, query):
        abe=AstBoolEvaluator()
        variabs=self.buildKnownVars(patient, entry)
        for q in Question.objects.all(): 
            variabs[q.code]=False
        for q in entry.question_set.all(): 
            variabs[q.code]=True        
        active=[]
        for c in Criteria.objects.all():
            #log.info("Evaluating criteria: %s [%s]" % (c.code, c.if_clause))
            v=variabs.copy()
            cond=c.if_clause.replace(".dd","").replace(".count","_count").replace(".td","").replace(".md","").replace(" OR "," or ").replace(" AND "," and ").replace(" NOT "," not ").strip()
            if cond.startswith("NOT "):        # condition can start with "not ..." 
                cond="not "+cond[4:]
            val=abe.evaluate(cond, v)
            variabs[c.code]=True if val else False
        # now evaluate the query
        v=variabs.copy()
        cond=query.replace(".dd","").replace(".count","_count").replace(".td","").replace(".md","").replace(" OR "," or ").replace(" AND "," and ").replace(" NOT "," not ").strip()
        val=abe.evaluate(cond, v)
        return True if val else False
    
    def getAntiholinergics (self):
        if self.antiholinergics:
            return self.antiholinergics
        if os.name=="nt":
            filePrefix='C:\WORK\Savin\StartStopp\doc\\'
        else:
            filePrefix='../doc/'
        fname=filePrefix+'Dottoressa - Antikulinergiki.csv'
        log.info("Loading antiholinergics...")
        self.antiholinergics={}
        with open(fname, 'rb') as csvfile:
            log.info("%s opened OK, reading file..." % (fname,))
            reader = UnicodeCsvReader(csvfile, delimiter=',', quotechar='"')
            rowCount=0
            for row in reader:
                rowCount=rowCount+1
                #if rowCount==1: continue
                # print row
                self.antiholinergics[ row[0] ] = int( row[1] )
            log.info("Antiholinergics read OK, %d lines" % (rowCount,))
        return self.antiholinergics
    
    def calcAntiholinergicLoad (self, e):
        ah=self.getAntiholinergics()
        ahLoad=0
        ahList=[]
        for de in DrugEntry.objects.filter(entry=e):
            # for all drugs in entry
            d=de.drug
            if d.atc in ah:
                al=ah[d.atc]
                ahList.append( {'name': d.name, 'load': al, 'atc': d.atc} )
                ahLoad=ahLoad+al
                log.info("Drug %s detected, ATC=%s, with antiholinergic load %d" % (d.name, d.atc, al))
        log.info("Total antiholinergic load is %d" % (ahLoad,))
        return (ahLoad, ahList)

ViewGlobals=ViewGlobalsClass()    
    
################################################################################
#                           COMMON FUNCTIONS
################################################################################

def is_root_access_allowed (request):
    """ returns true if access to a root web page is allowed """
    return (request.user.is_superuser or request.user.is_staff) and request.user.is_active

def is_access_allowed (request,doctorId):
    """ returns true if access to a doctor web page is allowed """
    if request.user.is_superuser and request.user.is_active:
        return True
    try:
        doctor=Doctor.objects.get(user__username=request.user.username)
    except:
        return False
    return doctor.id==int(doctorId) and request.user.is_active
    
################################################################################
#                              CSV DATA LOADING
################################################################################

def loadDiseases (fname):
    log.info("Trying to open %s..." % (fname,))
    allCodes=[d.code for d in Disease.objects.all()]
    updated, added, deleted = 0,0,0
    with open(fname, 'rb') as csvfile:
        log.info("Opened OK, reading file...")
        reader = UnicodeCsvReader(csvfile, delimiter=',', quotechar='"')
        rowCount=0
        for row in reader:
            rowCount=rowCount+1
            #if rowCount==1: continue
            # print row
            diseases=Disease.objects.filter(code=row[0])
            if diseases:
                d=diseases[0]  # only one, primary key!
                d.group_si=row[1]
                d.description_si=row[2]
                d.group_en=row[3]
                d.description_en=row[4]
                d.displaycode=row[5]
                updated=updated+1
                allCodes.remove(row[0])
                log.info("Disease %s [%s/%s] (group %s/%s) %s updated" % (d.code, d.description_en,  d.description_si, d.group_en, d.group_si, d.displaycode))
            else:
                d=Disease(code=row[0], group_si=row[1], description_si=row[2], group_en=row[3], description_en=row[4], displaycode=row[5])
                log.info("Disease %s [%s/%s] (group %s/%s) %s added" % (d.code, d.description_en,  d.description_si, d.group_en, d.group_si, d.displaycode))
                added=added+1
            d.save()
        for c in allCodes:
            Disease.objects.filter(code=c).delete()
            deleted=deleted+1
        log.info("Diseases read OK, %d lines (%d added, %d updated, %d deleted)" % (rowCount,added,updated,deleted))

def loadDrugGrups (fname):
    log.info("Trying to open %s..." % (fname,))
    allNames=[dg.name for dg in DrugGroup.objects.all()]
    updated, added, deleted = 0,0,0
    with open(fname, 'rb') as csvfile:
        log.info("Opened OK, reading file...")
        reader = UnicodeCsvReader(csvfile, delimiter=',', quotechar='"')
        rowCount=0
        for row in reader:
            rowCount=rowCount+1
            log.info("Parsing [%s]" % (row,))
            #if rowCount==1: continue
            nm=row[0].upper()
            dg=DrugGroup.objects.filter(name=nm)
            if dg:
                dg=dg[0]    # only one, primary key
                dg.column=row[2]
                dg.keywords=row[3].lower()
                #print "REMOVING ", nm, " from ", allNames
                allNames.remove(nm)
                updated=updated+1
            else:
                dg=DrugGroup(name=row[0].upper(), column=row[2], keywords=row[3])
                dg.keywords=row[3].lower()                
                log.info("Drug group %s column %s keywords %s added" % (dg.name, dg.column, dg.keywords))
                added=added+1
            if not dg.keywords:
                raise Exception("%s has no keywords at column=%s !" % (dg.name, dg.column))
            dg.save()
        for d in allNames:
            DrugGroup.objects.filter(name=d).delete()
            deleted=deleted+1
        log.info("Drug groups read OK, %d lines (%d added, %d updated, %d deleted)" % (rowCount,added,updated,deleted))
        
def loadDrugs1 (fname):    
    #Drug.objects.all().delete()
    log.info("Trying to open %s..." % (fname,))
    groups=[ (g.name, g.column, g.keywords) for g in DrugGroup.objects.all()]
    drugGroups={}
    for g in groups:
        drugGroups[g[0]]=[]     # group name is a key
        
    with open(fname, 'rb') as csvfile:
        log.info("Opened OK, reading file...")
        reader = UnicodeCsvReader(csvfile, delimiter=',', quotechar='"')
        rowCount=0
        for row in reader:
            rowCount=rowCount+1
            if rowCount==1: continue        # has header row!
            d=Drug.objects.filter(code=row[0])
            # find most appropriate name
            if row[3]: nm=row[3]
            elif row[2]: nm=row[2]
            elif row[1]: nm=row[1]
            nm=nm.replace(">","&gt;").replace("<","&lt;")            
            # use some heuristics to determine a per-unit dose
            m=re.search("(\d+)\s*(mg|mcg|g)",nm)
            if m is None:
                #log.info("%s: can't find per-unit dose, setting default!" % (d.name))
                dpu=0.0
            else:
                if m.group(2)=="mcg": dpu=0.001*int(m.group(1))
                elif m.group(2)=="mg": dpu=int(m.group(1))
                elif m.group(2)=="g": dpu=1000*int(m.group(1))
                else: raise TypeError("??? regexp failed !!!")                
            if d:
                d=d[0]  # only one, primary key
                d.name=nm
                d.unit=row[6]
                d.atc=row[8]
                d.doseperunit=dpu
            else:
                d=Drug(code=row[0], name=nm, unit=row[6], atc=row[8], doseperunit=dpu)
            d.save()
            code=row[0]     # this is a string, d.code may be int!                
            # find if drug matches a name in drug groups
            #print "DRUG:::", d.name
            for groupName,column,strings in groups:
                try:                            
                    colValue=row[ ord(column)-ord('A') ].strip().upper()
                    if not colValue:
                        #log.info("%s has no keywords at column=%s !" % (d.name, column))
                        continue
                    for s in strings.split(","):
                        s1=s.strip()     
                        #print "COL=",colValue, "STR=",s1                        
                        if not s1:
                            continue
                        if s1 in colValue.strip().lower():
                            #log.info("%s: found for %s (%s)" % (d.name, groupName, s1))
                            if d.doseperunit==0.0:
                                log.warning("%s [%s]: can't find per-unit dose, doses may not be calculated ok!" % (d.name, groupName))                                
                            drugGroups[groupName].append(code)
                            dg=DrugGroup.objects.filter(name=groupName)[0]
                            d.groups.add(dg)
                except:
                    log.error("Can't put drug %s to lists %s" % (d.name, groupName))
                    raise
        log.info("Read OK, %d lines." % (rowCount,))        
        for g in groups:
            drugs=drugGroups[g[0]]
            dgs=",".join(drugs)
            if len(dgs)>60: dgs=dgs[:60]+"..."
            log.info("%s : %d drugs [%s]" % (g, len(drugs), dgs))
    return drugGroups    

def loadCriteria (fname):
    allCodes=[c.code for c in Criteria.objects.all()]
    log.info("Trying to open %s..." % (fname,))
    updated, added, deleted = 0,0,0
    with open(fname, 'rb') as csvfile:
        log.info("Opened OK, reading file...")
        reader = UnicodeCsvReader(csvfile, delimiter=',', quotechar='"')
        rowCount=0
        for row in reader:
            rowCount=rowCount+1
            #if rowCount==1: continue
            c=Criteria.objects.filter(code=row[0])
            if c:
                c=c[0]  # only one, primary key
                c.versions=row[1]
                c.if_clause=row[2]
                c.description_si=row[3]
                c.description_en=row[4]
                allCodes.remove(row[0])
                updated=updated+1
            else:
                c=Criteria(code=row[0], versions=row[1], if_clause=row[2], description_si=row[3], description_en=row[4])
                log.info("Criteria %s [%s %s,SI:%s,EN:%s] added" % (c.versions, c.code, c.description_si, c.description_en, c.if_clause))
                added=added+1
            c.save()
        for c in allCodes:
            Criteria.objects.filter(code=c).delete()
            deleted=deleted+1
        log.info("Criteria read OK, %d lines (%d added, %d updated, %d deleted)" % (rowCount,added,updated,deleted))
    ViewGlobals.parseAllCriteria()
    
def loadQuestions (fname):
    log.info("Trying to open %s..." % (fname,))
    allCodes=[q.code for q in Question.objects.all()]
    updated, added, deleted = 0,0,0
    with open(fname, 'rb') as csvfile:
        log.info("Opened OK, reading file...")
        reader = UnicodeCsvReader(csvfile, delimiter=',', quotechar='"')
        rowCount=0
        for row in reader:
            rowCount=rowCount+1
            #if rowCount==1: continue
            desc_si=escape(row[1]) #row[1].replace(">","&gt;").replace("<","&lt;")
            desc_en=escape(row[2]) #row[2].replace(">","&gt;").replace("<","&lt;")
            q=Question.objects.filter(code=row[0])
            if q:
                q=q[0]  # only one, primary key
                q.description_si=desc_si
                q.description_en=desc_en
                allCodes.remove(row[0])
                updated=updated+1
            else:
                q=Question(code=row[0], description_si=desc_si, description_en=desc_en)
                log.info("Question %s [EN:%s] [SI:%s] added" % (q.code, q.description_en, q.description_si))
                added=added+1
            q.save()
        for c in allCodes:
            Question.objects.filter(code=c).delete()
            deleted=deleted+1
        log.info("Question read OK, %d lines (%d added, %d updated, %d deleted)" % (rowCount,added,updated,deleted))


################################################################################
#                               CVS EXPORT
################################################################################

def findMatch (matchLevel,  dataAdd1, fn, ln, yob):
    match=0
    for row in dataAdd1:
        ime_priimek=row[1].strip()
        try: 
            leto=int(row[3].strip())
        except:
            leto=yob # not entered?!            
        ime_priimek_split=ime_priimek.split()
        if len(ime_priimek_split)>=2:
            ips0=ime_priimek_split[0].upper()
            ips1=ime_priimek_split[1].upper()            
            if matchLevel==0:
                if (fn==ips0 and ln==ips1 and yob==leto) or \
                   (fn==ips1 and ln==ips0 and yob==leto):
                    log.info("... PERFECT matched to %s : %s" % (ime_priimek, leto))
                    match+=1
            if matchLevel==1:
                if (fn==ips0 and ln==ips1) or \
                   (fn==ips1 and ln==ips0):
                    log.info("... matched to %s : %s, years mismatch" % (ime_priimek, leto))
                    match+=1
            if matchLevel==2:
                if len(fn)<3 or len(ln)<3 or len(ips0)<3 or len(ips1)<3:
                    continue
                if (fn in ime_priimek_split[0].upper() and ln in ime_priimek_split[1].upper()) or \
                   (fn in ime_priimek_split[1].upper() and ln in ime_priimek_split[0].upper()) or \
                   (ime_priimek_split[0].upper() in fn and ime_priimek_split[1].upper() in ln) or \
                   (fn in ime_priimek_split[1].upper() and ime_priimek_split[0].upper() in ln):
                    log.info("... matched to %s : %s, partial name match" % (ime_priimek, leto))
                    match+=1            
        if len(ime_priimek_split)==1 and len(ime_priimek)==2:
            # initials only
            i=ime_priimek_split[0].upper()
            if matchLevel==3:
                if ((i[0]==fn[0] and i[1]==ln[0]) or (i[1]==fn[0] and i[0]==ln[0])) and yob==leto:
                    log.info("... matched to %s : %s, initials match" % (ime_priimek, leto)) 
                    match+=1                                               
    return (match==1)

def addCsvDataset (fname, phase):
    log.info("Trying to open %s..." % (fname,))
    # first Irena dataset
    dataAdd={}
    header=[]
    phaseStr="_%d," % (phase,)
    with open(fname, 'rb') as csvfile:
        log.info("Opened OK, reading file...")
        reader = UnicodeCsvReader(csvfile, delimiter=',', quotechar='"')
        rowCount=0
        for row in reader:
            if rowCount==0:
                header=phaseStr.join(row[5:])   # prenasamo od polja 5 naprej !
            else:
                dataAdd[row[0]]=row     # row 0 is patient ID = key !
            rowCount=rowCount+1
        log.info("Additional DB read OK, %d lines, header=%s" % (rowCount,header))
    header+="_%d" % (phase,)
    return (header, dataAdd)

def exportMatch (patientId, dataAdd, numHeader):
    match=False       
    addData=[]
    if patientId in dataAdd:
        r=dataAdd[patientId]
        log.info("Matched to %s : %s, %d columns" % (r[2], r[4], len(r)))
        match=True
        # use "" in fields with commas
        for x in r[5:]:     # zacnemo s poljem Z2 !!!
            if ',' in x:
                log.info("Matching column %s escaped" % (x,))
                addData.append('"'+x+'"')
            else:
                addData.append(x) 
    else:
        addData=[]*numHeader
    return match, addData            

def joinWith (x, postfix):
    return postfix.join(x) + postfix

def exportCsvQuerySet (reqeust, querySet):
    # generate required data
    head_pat=["NUM","NAME","SURNAME","YEAR_OF_BIRTH","AGE","MALE","FEMALE","NUM_ENTRIES","RESEARCH","CONTROL","INACTIVE"]
    head_entry_start=["NUM_DRUGS","NUM_PATIENT_KNOWS"]
    head_entry_end=["ENTRY_DATE", "AGE"]
    
    allDiseaseCodes=[d.code for d in Disease.objects.all()]
    allCriteriaCodes=[c.code for c in Criteria.objects.all()]
    
    # additional CSV file
    
    if os.name=="nt":
        filePrefix='C:\WORK\Savin\StartStopp\doc\\'
    else:
        filePrefix='../doc/'
    header1, dataAdd1 = addCsvDataset( filePrefix+'Baza Eva Gorup 2014.csv', 1 )
    header2, dataAdd2 = addCsvDataset( filePrefix+'Baza Eva Gorup 2016.csv', 2 )
    
    h1_baza=joinWith(head_entry_start, "_1,") + joinWith(allDiseaseCodes, "_1,") + "NUM_BROKEN_CRITERIA_1," + joinWith(allCriteriaCodes,"_1,")
    h1=h1_baza+header1+","+joinWith(head_entry_end,"_1,")[:-1]   # drop last ","
    h2_baza=joinWith(head_entry_start, "_2,") + joinWith(allDiseaseCodes, "_2,") + "NUM_BROKEN_CRITERIA_2," + joinWith(allCriteriaCodes,"_2,")
    h2=h2_baza+header2+","+joinWith(head_entry_end,"_2,")[:-1]   # drop last ","
        # h1 and h2 end with ","
    data=joinWith(head_pat, ",")    # ends with ","
    data+= h1+","+h2+"\n"
    
    numHeader2All=len(h2.split(","))
    numHeader1=len(header1.split(","))
    numHeader2=len(header2.split(","))
    numH2Baza=len(h2_baza.split(","))
    matched, unmatched=0, 0
    skip=True
    for p in querySet:
        line=""
        starost=datetime.now().year - p.year_of_birth
        line += "%s,%s,%s,%d,%d," % (p.id, p.first_name.strip(), p.last_name.strip(), p.year_of_birth, starost)
        if p.gender=="M": 
            male, female=1,0
        else:
            male, female=0,1
        line += "%d,%d," % (male, female)
        entries=Entry.objects.filter(patient=p.id)
        ec=len(entries)
        line += "%d," % (ec,)
        pacStr="%s: %s %s, %d" % (p.id, p.first_name, p.last_name, p.year_of_birth)
        if p.status=="R":
            research, control, inactive=1,0,0
        elif p.status=="C":
            research, control, inactive=0,1,0
        elif p.status=="I":
            research, control, inactive=0,0,1
        else:
            log.warning("Patient %s not in research, skipping..." % (pacStr))
            continue
        if ec==1:
            log.warning("Patient %s has only one entry" % (pacStr))
        elif ec!=2:
            log.warning("Patient %s has not exactly 2 entries (%d)" % (pacStr, ec))
        skip=False
        line += "%d,%d,%d," % (research, control, inactive)        
        fn=p.first_name.strip().upper()
        ln=p.last_name.strip().upper()
        log.info("Patient %s, finding match #1..." % (pacStr))
        match1, addData1=exportMatch(str(p.id), dataAdd1, numHeader1)
        if not match1:
            log.warning("NO MATCH #1 FOUND for %s" % (pacStr))
            unmatched+=1
            addData1=[]
            for i in range(numHeader1): 
                addData1.append('')
        log.info("Patient %s, finding match #2..." % (pacStr))
        match2, addData2=exportMatch(str(p.id), dataAdd2, numHeader2)
        if not match2:
            log.warning("NO MATCH #2 FOUND for %s" % (pacStr))
            unmatched+=1
            addData2=[]
            for i in range(numHeader2):
                addData2.append('')
        matched+=1
        entNum=1
        for e in entries:
            drugEntries=DrugEntry.objects.filter(entry=e.id)
            knows, drugs=0, 0
            for de in drugEntries:
                drugs += 1
                if de.patient_knows=="Y":
                    knows += 1
            dateEntry=datetime.strftime(e.dt, "%Y/%m/%d")     # SPSS compatible              
            line += "%d,%d," % (drugs, knows)        
            diseases=Disease.objects.filter(entries__id=e.id)
            entryDiseaseCodes=[d.code for d in diseases]
            for disCode in allDiseaseCodes:
                if disCode in entryDiseaseCodes:
                    line += "1,"
                else:
                    line += "0,"
            crb=ViewGlobals.getBrokenCriteria(p, e)
            criteria_v1=[c.code for c in Criteria.objects.filter(code__in=crb).filter(versions__contains="A")]
            log.info("Broken criteria: %s" % (str(crb),))
            tmp=""
            broken=0
            for critCode in allCriteriaCodes:
                if critCode in criteria_v1:
                    broken += 1
                    tmp += "1,"
                else:
                    tmp += "0,"
            line += ("%d," % (broken,)) + tmp       #[:-1]      # strip trailing comma
            # additional fields from head_entry_end
            star_entry=e.dt.year - p.year_of_birth
            if entNum==1:
                #log.warning("Joining data 1:%s" % (",".join(addData1)))
                line += joinWith(addData1,",")
            if entNum==2:
                #log.warning("Joining data 2:%s" % (",".join(addData2)))
                line += joinWith(addData2,",")
            line += "%s,%d" % (dateEntry, star_entry)
            if entNum==2:
                break
            else:
                line += ","
            entNum=entNum+1
        if ec==1:
            line +="," * (numH2Baza-1)  # skip trailing ","
            line += joinWith(addData2,",")
            line += "," # dateEntry, star_entry
        if not skip:
            data += line + "\n"
        
    log.info("MATCHED: %d, UNMATCHED: %d" % (matched, unmatched))
    # this is a pile of steaming crap. The utf8 support in browsers sucks.        
    fileName = "startstopp-export.csv"
    fileName = urllib2.quote(fileName.encode("utf8"));
    # look at this syntax... Ugly as hell! Which browsers actually support this?
    response = HttpResponse(data, content_type='text/csv')
    response['Content-Disposition'] = "attachment; filename*=UTF8''%s" % (fileName,)
    return response

def exportCsv (request):
    log.info("exportCsv")
    return exportCsvQuerySet (request, Patient.objects.all())

def exportCsvQuery (request, queryId):
    log.info("exportCsvQuery "+queryId)
    s=file(queryId,"r").read()
    pacIds=map(int, s.split(","))
    patients=Patient.objects.filter(id__in=pacIds)
    return exportCsvQuerySet (request, patients)

def exportAHQuerySet (request, querySet):
    log.info("exportAH query set")
    head_pat=["NUM","NAME","SURNAME","YEAR_OF_BIRTH","AGE","MALE","FEMALE","NUM_ENTRIES","RESEARCH","CONTROL","INACTIVE"]
    head_entry=["NUM_DRUGS","NUM_PATIENT_KNOWS", "ENTRY_NUM," "ENTRY_DATE", "ENTRY_AGE", "AH_LOAD"]
    
    anitholinergics=ViewGlobals.getAntiholinergics()
    ah_hdr=list(anitholinergics.keys())     # atc codes
    
    data=joinWith(head_pat, ",")    # ends with ","
    data+=joinWith(head_entry, ",")    # ends with ","
    data+=",".join(ah_hdr)+"\n"

    for p in querySet:
        pac=""
        starost=datetime.now().year - p.year_of_birth
        pac += "%s,%s,%s,%d,%d," % (p.id, p.first_name.strip(), p.last_name.strip(), p.year_of_birth, starost)
        if p.gender=="M": 
            male, female=1,0
        else:
            male, female=0,1
        pac += "%d,%d," % (male, female)
        entries=Entry.objects.filter(patient=p.id)
        ec=len(entries)
        pac += "%d," % (ec,)
        pacStr="%s: %s %s, %d" % (p.id, p.first_name, p.last_name, p.year_of_birth)
        if p.status=="R":
            research, control, inactive=1,0,0
        elif p.status=="C":
            research, control, inactive=0,1,0
        elif p.status=="I":
            research, control, inactive=0,0,1
        else:
            log.warning("Patient %s not in research, skipping..." % (pacStr))
            continue
        pac += "%d,%d,%d," % (research, control, inactive)        
        entNum=1
        for e in entries:
            drugEntries=DrugEntry.objects.filter(entry=e.id)
            knows, drugs=0, 0
            for de in drugEntries:
                drugs += 1
                if de.patient_knows=="Y":
                    knows += 1
            dateEntry=datetime.strftime(e.dt, "%Y/%m/%d")     # SPSS compatible              
            line = pac + "%d,%d," % (drugs, knows)           
            star_entry=e.dt.year - p.year_of_birth
            line += "%d,%s,%d," % (entNum, dateEntry, star_entry)
            entNum=entNum+1
            
            ahLoad, ahList=ViewGlobals.calcAntiholinergicLoad(e)
            line += "%d," % (ahLoad,)
            
            ahTable=[0]*len(ah_hdr)     # atc codes
            for ah in ahList:   # for all AH drugs
                idx=ah_hdr.index(ah['atc'])     # find correct ATC code index in table
                ahTable[idx]=ahTable[idx]+ah['load']
            line += ",".join( str(x) for x in ahTable )            
            data += line + "\n"
    
    fileName = "startstopp-antiholinergics.csv"
    fileName = urllib2.quote(fileName.encode("utf8"));
    # look at this syntax... Ugly as hell! Which browsers actually support this?
    response = HttpResponse(data, content_type='text/csv')
    response['Content-Disposition'] = "attachment; filename*=UTF8''%s" % (fileName,)
    return response

def exportAH (request):
    log.info("exportAH")
    return exportAHQuerySet(request, Patient.objects.all())


################################################################################
#                        PATIENTS SEARCH BY QUERY
################################################################################

def patientsQuery (query, entries):       
    # find result set
    pacIds=[]
    log.info("QUERY: %s" % (query,))
    for pac in Patient.objects.all():
        allEntries=Entry.objects.filter(patient_id=pac.id).order_by('dt')
        entryNo=1
        for ent in allEntries:
            log.info("Evaluating patient %s entry %d" % (pac.id, entryNo))
            if entryNo in entries:
                if ViewGlobals.matchesQuery(pac, ent, query):
                    pacIds.append(pac.id)
                    log.info("Patient %s entry %d MATCHES!!!" % (pac.id, entryNo))
            entryNo=entryNo+1
    # store into temporary file
    s=",".join( map(str, pacIds) )
    f=tempfile.NamedTemporaryFile(prefix="start-stopp-", delete=False)
    fileName=f.name
    f.file.write(s)
    # show result set from this temporary file
    return redirect("/showQuery/"+fileName)

def showQuery (request, queryId):
    """ shows query results from temporary file """
    log.info("showQuery "+queryId)
    if not request.user.is_authenticated():
        return redirect("/login")    
    s=file(queryId,"r").read()
    pacIds=map(int, s.split(","))
    patients=Patient.objects.filter(id__in=pacIds)
    return render_to_response('doctor/findpatients.html', 
        {
            'queryid': queryId, 
            'patients': patients,
            'numfound': len(patients),
            'root': is_root_access_allowed(request),
        }, 
        context_instance=RequestContext(request))           


################################################################################
#                                  VIEWS
################################################################################
    

class FindPacientForm(forms.Form):
    pacid = forms.CharField(label=_('Find patient'), max_length=6)
    
class FindByQueryForm(forms.Form):
    pacquery = forms.CharField(label=_('Find by query'), max_length=200)
    entries = forms.CharField(label=_('Entries'), max_length=15)
    
    
def showIndex (request):
    """ index: shows index.html for admins and home page for doctors """
    log.info("showIndex")
    if not request.user.is_authenticated():
        return redirect("/login")
    if is_root_access_allowed(request):
        querySet=Doctor.objects.annotate(
            models.Count('patient'),     # produces patient__count attribute for each doctor in query set!
            entry_first=models.Min('patient__entry__dt'))                
        findPacForm = FindPacientForm()
        findByQueryForm = FindByQueryForm()
        if request.method == 'POST':
            if u"FIND_PAC" in request.POST:
                # create a form instance and populate it with data from the request
                findPacForm = FindPacientForm(request.POST)
                if findPacForm.is_valid():
                    # process the data in form.cleaned_data as required
                    pacid = findPacForm.cleaned_data['pacid']
                    # find patient
                    pacients=Patient.objects.filter(id=pacid)
                    if len(pacients)==1:
                        pac=pacients[0]
                        return redirect('/doctor/%d/%d' % (pac.doctor.id, pac.id))
            elif u"FIND_BYQUERY" in request.POST:
                # create a form instance and populate it with data from the request
                findByQueryForm = FindByQueryForm(request.POST)
                if findByQueryForm.is_valid():
                    # process the data in form.cleaned_data as required
                    query = findByQueryForm.cleaned_data['pacquery']
                    ent_s=findByQueryForm.cleaned_data['entries'].split(",")
                    entries = [int(x) for x in ent_s]
                    return patientsQuery(query, entries)
        return render_to_response('doctor/index.html', 
            { 
                'findpacform': findPacForm,
                'findbydrugsform': findByQueryForm,
                'doctors': querySet,
            }, 
            context_instance=RequestContext(request))        
    else:
        doctor=Doctor.objects.get(user__username=request.user.username)
        return redirect("/doctor/%s" % (doctor.id,))

def loadDrugs (request):
    """ handle file upload """
    if not is_root_access_allowed(request):
        return redirect("/login")
    filePrefix='../doc/'
    prefix=filePrefix+'Dottoressa - '
    loadDrugs1(filePrefix+'zdravilca.csv')
    return redirect("/")

def loadOther (request):
    """ handle file upload """
    if not is_root_access_allowed(request):
        return redirect("/login")
    if os.name=="nt":
        filePrefix='C:\WORK\Savin\StartStopp\doc\\'
    else:
        filePrefix='../doc/'
    prefix=filePrefix+'Dottoressa - '
    loadDiseases(prefix+'Bolezni.csv')
    loadQuestions(prefix+'Vprasanja.csv')
    loadCriteria(prefix+'Kriteriji.csv')
    loadDrugGrups(prefix+'Grupe.csv')
    return redirect("/")

def showDoctor (request, doctorId):
    if not request.is_ajax():
        log.info("showDoctor %s" % (doctorId,))
    if not is_access_allowed(request,doctorId):
        log.warning("Access not allowed, doctorId=%s user=%s" % (doctorId, request.user.username,))
        #print request.user.is_superuser, request.user.id, doctorId, request.user.is_active
        return redirect("/login")
    try:
        doctor=Doctor.objects.filter(id=doctorId).annotate(models.Count('patient'))[0]
        patients=Patient.objects.filter(doctor=doctorId).annotate(
            models.Count('entry'),   # entry__count
            entry_first=models.Min('entry__dt') )
        log.info("Doctor: %s" % (doctor.user.username,))
    except:
        log.exception("Error in showDoctor")
        return redirect("/")
    # produces patient__count attribute for selected doctor
    return render_to_response('doctor/doctor.html', 
        {
            'doctor': doctor,
            'patients': patients,
            'root': is_root_access_allowed(request),
        }, 
        context_instance=RequestContext(request))


class PatientForm (forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PatientForm, self).__init__(*args, **kwargs)
        self.fields['first_name'].label = _("Name")+u":"
        self.fields['last_name'].label = _("Surname")+u":"    
        self.fields['year_of_birth'].label = _("Date of Birth")+u":"    
        self.fields['gender'].label = _("Gender")+u":"
        self.fields['contact'].label = _("Contact")+u":"    
    class Meta:
        model = Patient
        fields = ['first_name', 'last_name', 'year_of_birth', 'gender', 'contact']
 
def addPatient (request, doctorId):
    if not request.is_ajax():
        log.info("addPatient doctor=%s" % (doctorId,))
    if not is_access_allowed(request,doctorId):
        return redirect("/login")
    try:
        doctor=Doctor.objects.filter(id=doctorId)[0]
    except:
        log.exception("Error in showDoctor")
        return redirect("/")
    if request.method == 'POST':        
        f = PatientForm(request.POST) # A form bound to the POST data
        if f.is_valid(): # All validation rules pass            
            # don't use f.save(), it does not fill the doctor field!
            newPatient = f.save(commit=False)
            newPatient.doctor = doctor
            newPatient.save()
            return redirect("/doctor/%s" % (doctorId,))
    else:
        f = PatientForm() # An unbound form
    return render_to_response('doctor/addpatient.html', 
    {
        'doctor': doctor,
        'patientform': f,
    }, 
    context_instance=RequestContext(request))

def showPatient (request, doctorId, patientId):
    if not request.is_ajax():
        log.info("showPatient %s %s" % (doctorId, patientId))
    if not is_access_allowed(request,doctorId):
        return redirect("/login")
    doctor=Doctor.objects.filter(id=doctorId)[0]    
    patient=Patient.objects.filter(id=patientId)[0]
    if patient.doctor!=doctor:    # WTF???
        log.warning("Doctor/patient mismatch doctor=%s patient=%s" % (doctorId, patientId))
        return redirect("/login")
    entries=Entry.objects.filter(patient=patientId)
    return render_to_response('doctor/patient.html', 
    {
        'doctor': doctor,
        'patient': patient,
        'entries': entries,
        'root': is_root_access_allowed(request),        
    }, 
    context_instance=RequestContext(request))
    
def deletePatient (request, doctorId, patientId):
    if not is_root_access_allowed(request):
        return redirect("/login")
    doctor=Doctor.objects.filter(id=doctorId)[0]
    patient=Patient.objects.filter(id=patientId)[0]
    if patient.doctor!=doctor:
        log.warning("Doctor/patient mismatch doctor=%s patient=%s" % (doctorId, patientId))
        return redirect("/login")
    patient.delete()
    return redirect('/doctor/%s' % (doctorId,))
    
def addEntry (request, doctorId, patientId):
    if not is_access_allowed(request,doctorId):
        return redirect("/login")
    log.info("addEntry %s %s" % (doctorId, patientId))
    doctor=Doctor.objects.filter(id=doctorId)[0]    
    patient=Patient.objects.filter(id=patientId)[0]
    if patient.doctor!=doctor:  # WTF???
        log.warning("Doctor/patient mismatch doctor=%s patient=%s" % (doctorId, patientId))
        return redirect("/login")
    e=Entry()
    e.patient=patient
    e.dt=datetime.utcnow().replace(tzinfo=utc)
    e.save()
    entryId=e.id
    return redirect('/doctor/%s/%s/%s' % (doctorId,patientId,entryId)) 
        # new entry created, redirect to editEntry
        
def doctorToDoseAmount (txt):
    """ try to understand some basic notations for number of tablets i.e.
      3 x 1; 1-2; 3x1; 3*1; 1,5; 1.5; 1 1/2; 3 x 1/2 
    """
    s=txt.strip()
    s=txt.replace(",",".")      # decimal sign
    # common form 3 x .... | 3krat ... | 3* ....     
    m=re.search("(?P<n>\d*)\s*(x|X|\*|krat)\s*(?P<rest>.*)", s)
    if m:
        mul=float(m.group("n"))
        s=m.group("rest")
        log.info("dose amount multiplier form %f x %s:" % (mul, s))
    else:
        mul=1.0
    # try to find 2 1/2 and alikes: 3+3/4, 5/2...
    m=re.search("((?P<x>(\d))(\s|\+)*){0,1}(?P<a>\d)/(?P<b>\d)", s)
    if m and m.group("a") and m.group("b"):
        a=float(m.group("a"))
        b=float(m.group("b"))
        if m.group("x"):
            x=float(m.group("x"))
        else:
            x=0.0
        log.info("dose amount div form %f x (%f+%f/%f):" % (mul,x,a,b))
        rval=mul*(x+a/b)
    else:
        # no idea, try to convert directly to float
        log.info("dose amount trivial form %s" % (s,))
        rval=mul*float(s)
    log.info("dose amount %s -> %f:" % (txt, rval))
    return rval
        
def editEntry (request, doctorId, patientId, entryId):
    if not is_access_allowed(request,doctorId):
        return redirect("/login")
    if request.is_ajax():
        if request.method=='GET':
            print "AJAX GET!"
            if ("drug_search" in request.path): # generate by jQuery autocomplete
                #print request.GET['term']
                #response_data=ViewGlobals.drugAutocomplete( request.GET["term"].upper() )
                response_data=ViewGlobals.drugAutocomplete(request.GET["term"].upper())
                #print json.dumps(response_data)
                return HttpResponse(json.dumps(response_data), content_type="application/json")
            elif ("drug_check" in request.path):  # generated by jQuery validate remote: handler
                return HttpResponse('true' if ViewGlobals.isDrug(request.GET["newdrug"]) else "false", 
                    content_type="application/json")
            elif ("dose_check" in request.path):  # generated by jQuery validate remote: handler
                try:
                    a=doctorToDoseAmount(request.GET["newdose"])
                except:
                    a=0.0
                return HttpResponse('true' if a>0.0 else "false", content_type="application/json")
            elif ("diseaseChecked" in request.path):  # generated by jQuery validate remote: handler
                print "DiseaseChecked"
                name=request.GET["name"]
                checked=request.GET["checked"]
                print "DiseaseChecked", name, checked
                try:                    
                    entry=Entry.objects.filter(id=entryId)[0]
                    disease=Disease.objects.filter(code=name)[0]
                    if (checked=="true"):
                        disease.entries.add(entry)
                    else:
                        disease.entries.remove(entry)
                    return HttpResponse('true', content_type="application/json")
                except:
                    log.exception("Can't set diseaseChecked")
                    return HttpResponse('false', content_type="application/json")
            else:
                log.warning("Entry unknown ajax %s %s" % (str(request.path), str(request.GET)))
        return ""
    doctor=Doctor.objects.filter(id=doctorId)[0]
    patient=Patient.objects.filter(id=patientId)[0]
    entry=Entry.objects.filter(id=entryId)[0]
    if patient.doctor!=doctor or entry.patient!=patient:
        log.warning("Doctor/patient/entry mismatch doctor=%s patient=%s entry=%s" % (doctorId, patientId, entryId))
        return redirect("/login")
    if request.method=='POST':
        if "next" in request.POST:
            log.info("Entry next >>> clicked...")
            #print request.POST
            entry.other_diseases=request.POST["otherdiseases"].strip()
            log.info("Other diseases: %s" % (entry.other_diseases,))
            entry.save()
            # store diseases in N:N table
            allDiseases=[]
            entry.disease_set.clear()
            for optCode, optVal in request.POST.iteritems():
                if optCode.startswith("B"):                        
                    try:                        
                        disease=Disease.objects.filter(code=optCode)[0]
                        disease.entries.add(entry)
                        allDiseases.append(optCode)
                    except:
                        log.error("Disease code %s not found???" % (optCode,))
            log.info("Diseases stored [%s]" % (str(allDiseases),))
            # do we need any additional questions
            qu, dups=ViewGlobals.getRequiredQuestions(patient, entry)
            if len(qu)==0:
                log.info("No additional questions, redirecting...")
                return redirect("entrydone.html")
            log.info("Displaying additional questions")
            return render_to_response('doctor/questions.html', 
            {
                'doctor': doctor,
                'patient': patient,
                'questions': qu,
                'duplicates': dups,
                'questionentries': [q.code for q in entry.question_set.all()],
            },
            context_instance=RequestContext(request))                
        if "next2" in request.POST:
            log.info("Entry next2 >>> clicked...")
            entry.question_set.clear()
            for optCode, optVal in request.POST.iteritems():
                if optCode.startswith("V"):                        
                    try:                        
                        question=Question.objects.filter(code=optCode)[0]
                        question.entries.add(entry)
                    except:
                        log.error("Question code %s not found???" % (optCode,))    
            log.info("Questions stored.")
            return redirect("entrydone.html")
        if "addDrug" in request.POST:
            # store drugs in N:N table
            nmdrg=''
            doze=''
            try:
                nmdrg=request.POST["newdrug"].strip()
                doze=request.POST["newdose"].strip()
                drgs=Drug.objects.filter(name=nmdrg)
                # due to duplicated drugs in original ZZZS list, there may be more than one entry that
                # matches 
                if len(drgs)<1:
                    raise KeyError('Drug not found in drugs list!')
                # take the first matching drug!
                drg=drgs[0]
                da = doctorToDoseAmount(doze)
                if da<=0.0:
                    raise ValueError
                entry_drugs_exist=DrugEntry.objects.filter(entry=entryId).filter(drug=drg)
                if len(entry_drugs_exist)>0:
                    log.warning("Duplicate drug %s entered!" % (drg,))
                else:
                    #print request.POST
                    de=DrugEntry()
                    de.dose_amount = da  
                    de.entry = entry
                    de.drug = drg
                    if "nateden" in request.POST["dosetime"]:   de.dose_time = 'T'
                    elif "namesec" in request.POST["dosetime"]: de.dose_time = 'M'
                    else: de.dose_time = 'D'
                    if "pkno" in request.POST["pk"]:   de.patient_knows = 'N'
                    else: de.patient_knows = 'Y'
                    de.save()
            except:
                # drug can't be coded, amount not positive integer
                log.exception("Drug entry failed drug=%s doze=%s" % (nmdrg, doze))
    if request.method=='GET':
        if "deleteDrug" in request.GET:
            log.info("DELETE DRUG!!!")
            try:
                deId=int(request.GET["deleteDrug"])
                DrugEntry.objects.filter(id=deId).delete()
                log.info("Deleted drug %s" % (str(deId)))
            except:
                log.exception("Drug entry delete failed")            
                pass
            
    entry_drugs=DrugEntry.objects.filter(entry=entryId)
    #print "DRUGS:::",entry_drugs
    entry_diseases=entry.disease_set.all()
    #print "DISEASES:::", entry_diseases
    #ViewGlobals.parseAllCriteria()
    ViewGlobals.buildDrugAutocompleteCache()
    diseases_groups=ViewGlobals.getDiseasesGroups()
    # allow edits for superuser or if patient has no group
    allowEdit=(patient.status=='E' or patient.status=='N' or is_root_access_allowed(request)
        or entry.dt.date()>=date(2015, 06, 20))
    dups=[]
    if not allowEdit:
        qu, dups=ViewGlobals.getRequiredQuestions(patient, entry)
        qe=[q.code for q in entry.question_set.all()]
    else:
        qu=[]
        qe={}
    return render_to_response('doctor/entry.html', 
    {
        'doctor': doctor,
        'patient': patient,
        'other_diseases': entry.other_diseases,
        'diseases_groups': diseases_groups,
        'drugentries': entry_drugs,
        'diseaseentries': [d.code for d in entry_diseases],
        'allowedit': allowEdit,
        'questions': qu,
        'duplicates': dups,
        'questionentries': [q.code for q in entry.question_set.all()],
        'root': is_root_access_allowed(request),
    }, 
    context_instance=RequestContext(request))
    
def hammingWeight (x):
    """ Calculates Hamming weight of a integer; this is number of 1's in its binary representation """
    count=0
    while (x):
        x = x & (x-1)
        count=count+1
    return count;

def genAB (sz):
    """ This returns array of all binary strings of size sz with the number of 1s equal to number of 0s;
    for sz=4: ['0011', '0101', '0110', '1001', '1010', '1100']    
    """ 
    rval=[]
    fmt="{0:0%db}" % sz
    for num in range(1<<sz):
        if hammingWeight(num)==sz/2:
            rval.append( fmt.format(num) )
    return rval
    
def randomization (doctor):
    block=doctor.rand_block.strip()
    if block=="":
        # time to select a new random block
        # random block may be of size 4 or size 6, just throw them together in mix
        allBlocks=genAB(4) + genAB(6)
        # get a random number
        random.seed()
        block=random.choice(allBlocks)
        log.info("New randomization block selected: %s" % (block,))
    # consume first (most left) number of a block; 1=research, 0=control group
    rval='R' if block[0]=='1' else 'C'
    log.info("Randomization returns: %s, remaining block: %s" % (rval, block[1:]))
    # store remaining numbers in a doctor's record
    doctor.rand_block=block[1:]
    doctor.save()
    return rval

def doneEntry (request, doctorId, patientId, entryId):
    if not is_access_allowed(request,doctorId):
        return redirect("/login")
    doctor=Doctor.objects.filter(id=doctorId)[0]
    patient=Patient.objects.filter(id=patientId)[0]
    entry=Entry.objects.filter(id=entryId)[0]
    if patient.doctor!=doctor or entry.patient!=patient:
        log.warning("Doctor/patient/entry mismatch doctor=%s patient=%s entry=%s" % (doctorId, patientId, entryId))
        return redirect("/login")
    crb=ViewGlobals.getBrokenCriteria(patient, entry)
    instructions_v1=[c.getDescription() for c in Criteria.objects.filter(code__in=crb).filter(versions__contains="A")]
    instructions_v2=[c.getDescription() for c in Criteria.objects.filter(code__in=crb).filter(versions__contains="B")]
    log.info("Broken criteria: %s" % (str(crb),))
    log.info("Language: %s" % (get_language(),))
    log.info("INSTRUCTIONS V1: %s" % (str(instructions_v1),))
    log.info("INSTRUCTIONS V2: %s" % (str(instructions_v2),))
    if 'v1' in request.GET:
        log.info("Only V1 instructions will be shown!")
        instructions_v2='HIDE'
    entry_drugs=DrugEntry.objects.filter(entry=entryId)
    entry_diseases=entry.disease_set.all()
    diseases_groups=ViewGlobals.getDiseasesGroups()
    ahLoad, ahList=ViewGlobals.calcAntiholinergicLoad(entry)
    qu, dups=ViewGlobals.getRequiredQuestions(patient, entry)
    qe=[q.code for q in entry.question_set.all()]
    if patient.status == 'E':
        if False:
            # phase 1:  decide what to do with patient
            if not (instructions_v1 or instructions_v2):
                # no criteria broken!
                patient.status='I'  # inactive
            else:
                # criteria broken. Use randomization to select a group
                # R-esearch or C-control !!!
                patient.status=randomization(doctor)
        else:
            # phase 2: new pations have 'NOT IN RESEARCH' status 
            patient.status='N'      
        patient.save()
    return render_to_response('doctor/entrydone.html', 
    {
        'doctor': doctor,
        'patient': patient,
        'entry': entry,
        'instructions_v1': instructions_v1,
        'instructions_v2': instructions_v2,
        'drugentries': entry_drugs,
        'diseases_groups': diseases_groups,
        'other_diseases': entry.other_diseases,
        'diseaseentries': [d.code for d in entry_diseases],
        'questions': qu,
        'duplicates': dups,
        'questionentries': [q.code for q in entry.question_set.all()],
        'show_critera_violations': True,
            # was in phase 1: patient.status == 'R' or patient.status == 'N' or is_root_access_allowed(request),
        'ah_load': ahLoad,
        'ah_list': ahList,
    }, 
    context_instance=RequestContext(request))


def deleteEntry (request, doctorId, patientId, entryId):
    if not is_root_access_allowed(request):
        return redirect("/login")
    doctor=Doctor.objects.filter(id=doctorId)[0]
    patient=Patient.objects.filter(id=patientId)[0]
    entry=Entry.objects.filter(id=entryId)[0]
    if patient.doctor!=doctor or entry.patient!=patient:
        log.warning("Doctor/patient/entry mismatch doctor=%s patient=%s entry=%s" % (doctorId, patientId, entryId))
        return redirect("/login")
    entry.delete()
    return redirect('/doctor/%s/%s' % (doctorId,patientId))
