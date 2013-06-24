#
# Copyright (C) 2007-2012 by Johan De Taeye, frePPLe bvba
#
# This library is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero
# General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import os.path
from datetime import datetime
from threading import Thread

from django.conf import settings
from django.core import management
from django.views.decorators.cache import never_cache
from django.shortcuts import render
from django.db.models import get_apps
from django.utils.translation import ugettext_lazy as _
from django.db import DEFAULT_DB_ALIAS, transaction
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_protect
from django.http import Http404, HttpResponseRedirect, HttpResponse
from django.contrib import messages
from django.utils.encoding import force_unicode

from freppledb.execute.models import log, Scenario
from freppledb.common.report import GridReport, GridFieldLastModified, GridFieldText, GridFieldInteger
from freppledb.common.models import Parameter

@staff_member_required
@csrf_protect
def main(request):
  '''
  This view implements the overview screen with all execution
  actions.
  '''
  try: constraint = int(request.session['constraint'])
  except: constraint = 15

  # Synchronize the scenario table with the settings
  Scenario.syncWithSettings()

  # Check if a plan is running
  try:
    progress = float(Parameter.objects.using(request.database).get(name="Plan executing").value)
  except:
    progress = 0

  # Loop over all fixtures of all apps and directories
  fixtures = set()
  folders = list(settings.TEMPLATE_DIRS)
  for app in get_apps():
    if app.__name__.startswith('django'): continue
    folders.append(os.path.join(os.path.dirname(app.__file__), 'fixtures'))
  for f in folders:
    try:
      for root, dirs, files in os.walk(f):
        for i in files:
          if i.endswith('.json'):
            fixtures.add(i.split('.')[0])
    except:
      pass # Silently ignore failures
  fixtures = sorted(fixtures)

  # Send to template
  return render(request, 'execute/execute.html', {
          'title': _('Execute'),
          'capacityconstrained': constraint & 4,
          'materialconstrained': constraint & 2,
          'leadtimeconstrained': constraint & 1,
          'fenceconstrained': constraint & 8,
          'scenarios': Scenario.objects.all(),
          'fixtures': fixtures,
          'progress': progress
          } )


@staff_member_required
@never_cache
@csrf_protect
def erase(request):
  '''
  Erase the contents of the database.
  '''
  # Allow only post
  if request.method != 'POST':
    messages.add_message(request, messages.ERROR, force_unicode(_('Only POST method allowed')))
    return HttpResponseRedirect('%s/execute/#database' % request.prefix)

  # Erase the database contents
  try:
    management.call_command('frepple_flush', user=request.user.username,
      nonfatal=True, database=request.database)
    messages.add_message(request, messages.INFO, force_unicode(_('Erased the database')))
  except Exception as e:
    messages.add_message(request, messages.ERROR, force_unicode(_('Failure during database erasing: %(msg)s') % {'msg':e}))

  # Redirect the page such that reposting the doc is prevented and refreshing the page doesn't give errors
  return HttpResponseRedirect('%s/execute/#database' % request.prefix)


@staff_member_required
@never_cache
@csrf_protect
def create(request):
  '''
  Create a sample model in the database.
  '''
  # Allow only post
  if request.method != 'POST':
    messages.add_message(request, messages.ERROR,
      force_unicode(_('Only POST method allowed')))
    return HttpResponseRedirect('%s/execute/#generator' % request.prefix)

  # Validate the input form data
  try:
    clusters = int(request.POST['clusters'])
    demands = int(request.POST['demands'])
    fcstqty = int(request.POST['fcst'])
    levels = int(request.POST['levels'])
    resources = int(request.POST['rsrc_number'])
    resource_size = int(request.POST['rsrc_size'])
    procure_lt = int(request.POST['procure_lt'])
    components_per = int(request.POST['components_per'])
    components = int(request.POST['components'])
    deliver_lt = int(request.POST['deliver_lt'])
    if clusters>100000 or clusters<=0 \
      or fcstqty<0 or demands>=10000 or demands<0 \
      or levels<0 or levels>=50 \
      or resources>=1000 or resources<0 \
      or resource_size>100 or resource_size<0 \
      or deliver_lt<=0 or procure_lt<=0 \
      or components<0 or components>=100000 \
      or components_per<0:
        raise ValueError("Invalid parameters")
  except KeyError:
    raise Http404
  except ValueError as e:
    messages.add_message(request, messages.ERROR,
      force_unicode(_('Invalid input field')))
  else:
    # Execute
    try:
      management.call_command('frepple_flush', user=request.user.username, nonfatal=True, database=request.database)
      management.call_command('frepple_createmodel',
        verbosity=0, cluster=clusters, demand=demands,
        forecast_per_item=fcstqty, level=levels, resource=resources,
        resource_size=resource_size, components=components,
        components_per=components_per, deliver_lt=deliver_lt,
        procure_lt=procure_lt, user=request.user.username,
        nonfatal=True, database=request.database
        )
      messages.add_message(request, messages.INFO,
        force_unicode(_('Created sample model in the database')))
    except Exception as e:
      messages.add_message(request, messages.ERROR,
        force_unicode(_('Failure during sample model creation: %(msg)s') % {'msg':e}))

  # Show the main screen again
  # Redirect the page such that reposting the doc is prevented and refreshing the page doesn't give errors
  return HttpResponseRedirect('%s/execute/#generator' % request.prefix)


class runfrepple_async(Thread):
  def __init__(self, request, plantype, constraint):
    self.request = request
    self.plantype = plantype
    self.constraint = constraint
    Thread.__init__(self)

  def run(self):
    try:
      management.call_command(
        'frepple_run',
        user=self.request.user.username,
        plantype=self.plantype, constraint=self.constraint,
        nonfatal=True, database=self.request.database
        )
      messages.add_message(self.request, messages.INFO,
        force_unicode(_('Successfully created a plan')))
    except Exception as e:
      messages.add_message(self.request, messages.ERROR,
        force_unicode(_('Failure creating a plan: %(msg)s') % {'msg':e}))


@staff_member_required
@never_cache
@csrf_protect
def runfrepple(request):
  '''
  FrePPLe execution button.
  '''
  # Allow only post
  if request.method != 'POST':
    messages.add_message(request, messages.ERROR,
      force_unicode(_('Only POST method allowed')))
    return HttpResponseRedirect('%s/execute/#plan' % request.prefix)

  # Decode form input
  constraint = 0
  for value in request.POST.getlist('constraint'):
    try: constraint += int(value)
    except: pass
  plantype = 1
  try: plantype = request.POST.get('plantype')
  except: pass

  # Update the session object
  request.session['plantype'] = plantype
  request.session['constraint'] = constraint

  # Run frePPLe in a separate Python thread
  p = Parameter.objects.using(request.database).get_or_create(name="Plan executing")[0]
  p.value = "1"
  p.save(using=request.database)
  runfrepple_async(request, plantype, constraint).start()

  # Redirect the page such that reposting the doc is prevented and refreshing the page doesn't give errors
  return HttpResponseRedirect('%s/execute/#plan' % request.prefix)


@staff_member_required
@never_cache
@csrf_protect
def cancelfrepple(request):
  '''
  FrePPLe cancel button.
  '''
  # Allow only post
  if request.method != 'POST':
    messages.add_message(request, messages.ERROR,
      force_unicode(_('Only POST method allowed')))
    return HttpResponseRedirect('%s/execute/#plan' % request.prefix)
  try:
    p = Parameter.objects.using(request.database).get(name="Plan executing")
    p.value = p.value + ' Canceling'
    p.save(using=request.database)
  except:
    pass
  return HttpResponseRedirect('%s/execute/#plan' % request.prefix)


@staff_member_required
@never_cache
@csrf_protect
def progressfrepple(request):
  '''
  FrePPLe progress bar.
  '''
  try:
    percentage = Parameter.objects.using(request.database).get(name="Plan executing").value
  except:
    percentage = 0
  return HttpResponse(
     mimetype = 'text/html; charset=%s' % settings.DEFAULT_CHARSET,
     content = percentage
     )
  return HttpResponseRedirect('%s/execute/#plan' % request.prefix)


@staff_member_required
@never_cache
@csrf_protect
def fixture(request):
  """
  Load a dataset stored in a django fixture file.
  """
  # Validate the request
  if request.method != 'POST':
    messages.add_message(request, messages.ERROR,
      force_unicode(_('Only POST method allowed')))
    # Redirect the page such that reposting the doc is prevented and refreshing the page doesn't give errors
    return HttpResponseRedirect('%s/execute/#database' % request.prefix)

  # Decode the input data from the form
  try:
    fixture = request.POST['datafile']
    if fixture == '-': raise
  except:
    messages.add_message(request, messages.ERROR,
      force_unicode(_('Missing dataset name')))
    return HttpResponseRedirect('%s/execute/#database' % request.prefix)

  # Load the fixture
  # The fixture loading code is unfornately such that no exceptions are
  # or any error status returned when it fails...
  try:
    log(category='LOAD', theuser=request.user.username,
      message='Start loading dataset "%s"' % fixture).save(using=request.database)
    management.call_command('loaddata', fixture, verbosity=0, database=request.database)
    messages.add_message(request, messages.INFO,
      force_unicode(_('Loaded dataset')))
    log(category='LOAD', theuser=request.user.username,
      message='Finished loading dataset "%s"' % fixture).save(using=request.database)
  except Exception as e:
    messages.add_message(request, messages.ERROR,
      force_unicode(_('Error while loading dataset: %(msg)s') % {'msg':e}))
    log(category='LOAD', theuser=request.user.username,
      message='Failed loading dataset "%s": %s' % (fixture,e)).save(using=request.database)
  return HttpResponseRedirect('%s/execute/#database' % request.prefix)


@staff_member_required
@never_cache
def logfile(request):
  '''
  This view shows the frePPLe log file of the last planning run in this database.
  '''
  try:
    if request.database == DEFAULT_DB_ALIAS:
      f = open(os.path.join(settings.FREPPLE_LOGDIR, 'frepple.log'), 'rb')
    else:
      f = open(os.path.join(settings.FREPPLE_LOGDIR, 'frepple_%s.log' % request.database), 'rb')
  except:
    logdata = "File not found"
  else:
    try:
      f.seek(-1, os.SEEK_END)
      if f.tell() >= 50000:
        # Too big to display completely
        f.seek(-50000, os.SEEK_END)
        logdata = force_unicode(_("Displaying only the last 50K from the log file")) + '...\n\n...' + f.read(50000)
      else:
        # Displayed completely
        f.seek(0, os.SEEK_SET)
        logdata = f.read(50000)
    finally:
      f.close()

  return render(request, 'execute/logfrepple.html', {
      'title': _('Log file'),
      'logdata': logdata,
      } )


class LogReport(GridReport):
  '''
  A list report to review the history of actions.
  '''
  title = _('Command log')
  basequeryset = log.objects.all()
  default_sort = (0,'desc')
  model = log
  frozenColumns = 0
  multiselect = False
  editable = False

  rows = (
    GridFieldInteger('id', title=_('identifier'), key=True),
    GridFieldLastModified('lastmodified'),
    GridFieldText('category', title=_('category'), editable=False, align='center'),
    GridFieldText('theuser', title=_('user'), editable=False, align='center'),
    GridFieldText('message', title=_('message'), editable=False, width=500),
    )


@staff_member_required
@transaction.commit_manually
@csrf_protect
def scenarios(request):
  '''
  This view implements the scenario management action.
  '''
  # Allow only post
  if request.method != 'POST':
    messages.add_message(request, messages.ERROR,
      force_unicode(_('Only POST method allowed')))
    return HttpResponseRedirect('%s/execute/#scenarios' % request.prefix)

  # Execute the correct action
  try:
    # ACTION 1: Updating the description
    if 'update' in request.POST:
      for sc in Scenario.objects.all():
        if request.POST.get(sc.name, 'off') == 'on':
          sc.description = request.POST.get('description',None)
          sc.save()
          messages.add_message(request, messages.INFO,
            force_unicode(_("Updated scenario '%(scenario)s'") % {'scenario': sc.name}))

    # ACTION 2: Copying datasets
    elif 'copy' in request.POST:
      source = request.POST.get('source', DEFAULT_DB_ALIAS)
      for sc in Scenario.objects.all():
        if request.POST.get(sc.name,'off') == 'on' and sc.status == u'Free':
          try:
            management.call_command(
              'frepple_copy',
              source,
              sc.name,
              user=request.user.username,
              nonfatal=True,
              force=True
              )
            messages.add_message(request, messages.INFO,
              force_unicode(_("Successfully copied scenario '%(source)s' to '%(destination)s'") % {'source': source, 'destination': sc.name}))
          except Exception:
            messages.add_message(request, messages.ERROR,
              force_unicode(_("Failure copying scenario '%(source)s' to '%(destination)s'") % {'source': source, 'destination':sc.name}))

    # ACTION 3: Release a copy
    elif 'release' in request.POST:
      for sc in Scenario.objects.all():
        if request.POST.get(sc.name,'off') == u'on' and sc.status != u'Free':
          sc.status = u'Free'
          sc.lastrefresh = datetime.today()
          sc.save()
          messages.add_message(request, messages.INFO,
            force_unicode(_("Released scenario '%(scenario)s'") % {'scenario': sc.name}))
          if request.database == sc.name:
            # Erasing the database that is currently selected.
            request.prefix = ''

    # INVALID ACTION
    else:
      messages.add_message(request, messages.ERROR,
        force_unicode(_('Invalid action')))
      return HttpResponseRedirect('%s/execute/#scenarios' % request.prefix)

  except Exception as x:
    print x
    transaction.rollback()
  finally:
    transaction.commit()

  # Redirect the page such that reposting the doc is prevented and refreshing the page doesn't give errors
  return HttpResponseRedirect('%s/execute/#scenarios' % request.prefix)
