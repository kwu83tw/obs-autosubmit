#!/usr/bin/env python
# vim: set ts=4 sw=4 et: coding=UTF-8

#
# Copyright (c) 2011-2012, SUSE, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#  * Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#  * Neither the name of the <ORGANIZATION> nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
#
# (Licensed under the simplified BSD license)
#
# Authors: Vincent Untz <vuntz@opensuse.org>
#

import os
import sys

import errno

import optparse
import re
import sqlite3
import traceback
import urllib
import urllib2
import urlparse

try:
    from lxml import etree as ET
except ImportError:
    try:
        from xml.etree import cElementTree as ET
    except ImportError:
        import cElementTree as ET


from osc import conf as oscconf
from osc import core


NO_DEVEL_PACKAGE_SAFE = [ '^_product.*' ]

# Not sure why, but it seems there's some black magic for this specific
# package: it's a link to openSUSE:Factory/glibc, but it's different
INTERNAL_LINK_DIFFERENT_HASH_SAFE = [ 'openSUSE:Factory/glibc.i686' ]


#######################################################################


NO_DEVEL_PACKAGE_SAFE_REGEXP = [ re.compile(x) for x in NO_DEVEL_PACKAGE_SAFE ]


#######################################################################


def safe_mkdir_p(dir):
    if not dir:
        return

    try:
        os.makedirs(dir)
    except OSError, e:
        if e.errno != errno.EEXIST:
            raise e


#######################################################################


class AutoSubmitException(Exception):
    pass

class AutoSubmitUnlikelyException(AutoSubmitException):
    pass


#######################################################################


class AutoSubmitConfig:

    def __init__(self, options):
        self.cache_dir = options.cache_dir or os.getcwd()
        self.apiurl = options.apiurl or 'https://api.opensuse.org/'
        self.project = options.project or 'openSUSE:Factory'
        self.verbose = options.verbose
        self.debug = options.debug


#######################################################################


def fetch_status_for_project(apiurl, project):
    url = core.makeurl(apiurl, ['status', 'project', project])

    try:
        fin = core.http_GET(url)
    except urllib2.HTTPError, e:
        raise AutoSubmitException('Cannot get status of %s: %s' % (project, e))

    try:
        node = ET.parse(fin).getroot()
    except SyntaxError, e:
        fin.close()
        raise AutoSubmitException('Cannot parse status of %s: %s' % (project, e))

    fin.close()

    return node


#######################################################################


def fetch_requests(apiurl, xpath):
    url = core.makeurl(apiurl, ['search', 'request'], ['match=%s' % urllib.quote_plus(xpath)])

    try:
        fin = core.http_GET(url)
    except urllib2.HTTPError, e:
        raise AutoSubmitException('Cannot get requests submitted to %s: %s' % (project, e))

    try:
        node = ET.parse(fin).getroot()
    except SyntaxError, e:
        fin.close()
        raise AutoSubmitException('Cannot parse requests submitted to %s: %s' % (project, e))

    fin.close()

    return node


def fetch_requests_for_project(apiurl, project, package = None):
    xpath = '(action/@type=\'submit\' or action/@type=\'delete\') and (state/@name=\'new\' or state/@name=\'review\') and (action/target/@project=\'%(project)s\' or submit/target/@project=\'%(project)s\')' % { 'project': project }

    return fetch_requests(apiurl, xpath)


def fetch_all_requests_for_package(apiurl, project, package):
    xpath = 'action/@type=\'submit\' and (action/target/@project=\'%(project)s\' or submit/target/@project=\'%(project)s\') and (action/target/@package=\'%(package)s\' or submit/target/@package=\'%(package)s\')' % { 'project': project, 'package': package }

    return fetch_requests(apiurl, xpath)


#######################################################################


def fetch_package_files_metadata(apiurl, project, package, revision = None, expand = False):
    query = {}
    if revision:
        query['rev'] = revision
    if expand:
        query['expand'] = '1'

    url = core.makeurl(apiurl, ['public', 'source', project, package], query=query)

    try:
        fin = core.http_GET(url)
    except urllib2.HTTPError, e:
        raise AutoSubmitException('Cannot get files metadata of %s/%s: %s' % (project, package, e))

    try:
        node = ET.parse(fin).getroot()
    except SyntaxError, e:
        fin.close()
        raise AutoSubmitException('Cannot parse files metadata of %s/%s: %s' % (project, package, e))

    fin.close()

    return node


#######################################################################


def fetch_package_info(apiurl, project, package, revision = None):
    query = {'view': 'info'}
    if revision:
        query['rev'] = revision

    url = core.makeurl(apiurl, ['public', 'source', project, package], query=query)

    try:
        fin = core.http_GET(url)
    except urllib2.HTTPError, e:
        raise AutoSubmitException('Cannot get info of %s/%s: %s' % (project, package, e))

    try:
        node = ET.parse(fin).getroot()
    except SyntaxError, e:
        fin.close()
        raise AutoSubmitException('Cannot parse info of %s/%s: %s' % (project, package, e))

    fin.close()

    return node


#######################################################################


def create_submit_request(apiurl, source_project, source_package, rev, target_project, target_package):
#TODO drop this
    return 0

    request = ET.Element('request')
    request.set('type', 'submit')

    submit = ET.SubElement(request, 'submit')

    source = ET.SubElement(submit, 'source')
    source.set('project', source_project)
    source.set('package', source_package)
    source.set('rev', rev)

    target = ET.SubElement(submit, 'target')
    target.set('project', target_project)
    target.set('package', target_package)

    state = ET.SubElement(request, 'state')
    state.set('name', 'new')

    description = ET.SubElement(request, 'description')
    description.text = 'Automatic submission by obs-autosubmit'

    tree = ET.ElementTree(request)
    xml = ET.tostring(tree)

    url = core.makeurl(apiurl, ['request'], query='cmd=create')

    try:
        fin = core.http_POST(url, data=xml)
    except urllib2.HTTPError, e:
        raise AutoSubmitException('Cannot submit %s to %s: %s' % (source_project, source_package, target_project, target_package, e))

    try:
        node = ET.parse(fin).getroot()
    except SyntaxError, e:
        fin.close()
        raise AutoSubmitException('Cannot parse result of submission of %s to %s: %s' % (source_project, source_package, target_project, target_package, e))

    fin.close()

    return node.get('id')


#######################################################################


class AutoSubmitPackage:
    '''
        Small note about the hashes:

         - unexpanded_hash: hash of the unexpanded sources
         - hash: this is, more or less, the hash of the expanded sources.
           ("more or less" because this is verifymd5, which is apparently used
           internally in OBS by the scheduler; it's not the hash we get by
           default)

        For all that matters, we're really interested in hash when comparing
        packages to see if there's a diff, not unexpanded_hash.
    '''

    def __init__(self, project, package, state_hash = '', unexpanded_state_hash = '', rev = '', changes_hash = ''):
        self.project = project
        self.package = package
        self.state_hash = state_hash
        self.unexpanded_state_hash = unexpanded_state_hash
        self.rev = rev
        self.changes_hash = changes_hash


    def fetch_latest_package_state(self, apiurl, nochanges = False):
        sourceinfo_node = fetch_package_info(apiurl, self.project, self.package)

        rev = sourceinfo_node.get('rev')
        unexpanded_state_hash = sourceinfo_node.get('srcmd5')
        state_hash = sourceinfo_node.get('verifymd5') or unexpanded_state_hash

        if not rev or not unexpanded_state_hash:
            raise AutoSubmitException('Cannot fetch current state of %s' % (self,))

        self.rev = rev
        self.unexpanded_state_hash = unexpanded_state_hash

        # State hash might be the same -- for instance, after "baserev update by copy to link target" commits from buildservice-autocommit
        # In that case, we don't need to fetch the new hash of the .changes file
        if state_hash == self.state_hash:
            # We were up-to-date, that's cool
            return

        self.state_hash = state_hash

        if nochanges:
            return

        # Update changes_hash
        directory_node = fetch_package_files_metadata(apiurl, self.project, self.package, expand = True)

        self.changes_md5 = None

        for entry_node in directory_node.findall('entry'):
            name = entry_node.get('name') or ''
            md5 = entry_node.get('md5')

            if name.endswith('.changes') and not md5:
                raise AutoSubmitException('Cannot fetch hash of changes file for %s' % (self,))

            if name == '%s.changes' % self.package:
                self.changes_md5 = md5
                break


    @classmethod
    def from_status_node(cls, node):
        project = node.get('project')
        package = node.get('name')
        unexpanded_md5 = node.get('srcmd5')
        expanded_md5 = node.get('verifymd5') or unexpanded_md5
        changes_md5 = node.get('changesmd5')

        if not expanded_md5:
            raise AutoSubmitUnlikelyException('no state hash for %s/%s (?)' % (project, package))

        return AutoSubmitPackage(project, package, state_hash = expanded_md5, unexpanded_state_hash = unexpanded_md5, changes_hash = changes_md5)


    @classmethod
    def from_status_develpack_node(cls, develpack_node):
        project = develpack_node.get('proj')
        package = develpack_node.get('pack')

        package_node = develpack_node.find('package')
        if package_node is not None:
            ret = AutoSubmitPackage.from_status_node(package_node)
            if ret.project == project and ret.package == package:
                return ret
            else:
                raise AutoSubmitUnlikelyException('inconsistent develpack and package nodes')
        else:
            raise AutoSubmitUnlikelyException('no package node in develpack node')


    @classmethod
    def from_request_node(cls, node):
        project = node.get('project')
        package = node.get('package')
        rev = node.get('rev')

        return AutoSubmitPackage(project, package, rev = rev)


    # Note: we do not use the state hash below; this makes it easy to know
    # if we're looking at the same package even if its content is different

    def __eq__(self, other):
        return self.project == other.project and self.package == other.package

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        return str(self) < str(other)

    def __le__(self, other):
        return self.__eq__(other) or self.__lt__(other)

    def __gt__(self, other):
        return other.__lt__(self)

    def __ge__(self, other):
        return other.__eq__(self) or other.__lt__(self)

    def __str__(self):
        return '%s/%s' % (self.project, self.package)


#######################################################################


class AutoSubmitCache:
    ''' The cache only contains packages with a difference as of now, with
        each of them belonging to one category:
          - the list of packages that we filtered (since they should stay
            ignored).
          - the list of packages that we successfully submitted (since they
            should be ignored now).
        We need to put the second category in there, else we'll rely on the
        "look at new submit requests" filter, which requires some traffic.

        See hash documentation in AutoSubmitPackage for why we use state_hash
        and not unexpanded_state_hash
    '''

    def __init__(self, conf):
        self.conf = conf
        self._dbfile = os.path.join(self.conf.cache_dir, 'cache.db')

        self.dbmeta = None
        self.cursor = None

        self._init_db()


    def _init_db(self):
        create = True
        if os.path.exists(self._dbfile):
            create = False
            if not os.access(self._dbfile, os.W_OK):
                raise AutoSubmitUnlikelyException('\'%s\' is read-only. Cache database must be writable.' % self._dbfile)
        else:
            dirname = os.path.dirname(self._dbfile)
            if not os.path.exists(dirname):
                os.makedirs(dirname)

        self.dbmeta = sqlite3.connect(self._dbfile)
        if not self.dbmeta:
            raise AutoSubmitUnlikelyException('No access to cache database.' % self._dbfile)

        self.dbmeta.row_factory = sqlite3.Row
        self.cursor = self.dbmeta.cursor()

        if create:
            self.cursor.execute('''CREATE TABLE cache (date TEXT, parent_project TEXT, parent_package TEXT, devel_project TEXT, devel_package TEXT, devel_state_hash TEXT);''')


    def get_from_cache(self, parent_project, parent_package):
        self.cursor.execute('''SELECT * FROM cache WHERE parent_project = ? AND parent_package = ?;''', (parent_project, parent_package))
        row = self.cursor.fetchone()
        if row:
            return (row['devel_project'], row['devel_package'], row['devel_state_hash'])
        else:
            return (None, None, None)


    def add_to_cache(self, parent_project, parent_package, devel_project, devel_package, devel_state_hash):
        # First remove old entries for this parent package
        self.cursor.execute('''DELETE FROM cache WHERE parent_project = ? AND parent_package = ?;''', (parent_project, parent_package))

        self.cursor.execute('''INSERT INTO cache VALUES (datetime('now'), ?, ?, ?, ?, ?);''', (parent_project, parent_package, devel_project, devel_package, devel_state_hash))


    def prune_old_entries(self):
        self.cursor.execute('''DELETE FROM cache WHERE datetime(date, '+7 days') < datetime('now');''')


    def commit(self):
        if self.dbmeta:
            self.dbmeta.commit()


    def __del__(self):
        if self.cursor:
            self.cursor.close()
        if self.dbmeta:
            self.dbmeta.commit()
            self.dbmeta.close()


#######################################################################


class AutoSubmitWorker:

    def __init__(self, conf):
        self.conf = conf


    def _verbose_print(self, s, level = 1):
        if self.conf.verbose >= level:
            print s


    def _fetch_packages_with_diff(self):
        xml_root = fetch_status_for_project(self.conf.apiurl, self.conf.project)

        with_diff_hash = {}
        self._packages_with_diff = []

        for package_node in xml_root.findall('package'):
            try:
                parent_package = AutoSubmitPackage.from_status_node(package_node)
            except AutoSubmitUnlikelyException, e: 
                print >>sys.stderr, 'Cannot get package: %s' % e
                continue

            if parent_package.project != self.conf.project:
                print >>sys.stderr, '%s found as parent package while auto-submitting to %s.' % (parent_package, self.conf.project)
                continue

            develpack_node = package_node.find('develpack')
            if develpack_node is None:
                safe = False
                for regexp in NO_DEVEL_PACKAGE_SAFE_REGEXP:
                    match = regexp.match(parent_package.package)
                    if match:
                        safe = True
                        break

                if not safe:
                    print >>sys.stderr, 'No devel package for %s.' % parent_package
                continue

            try:
                devel_package = AutoSubmitPackage.from_status_develpack_node(develpack_node)
            except AutoSubmitUnlikelyException, e: 
                print >>sys.stderr, 'Cannot get devel package for %s: %s' % (parent_package, e)
                continue

            # See hash documentation in AutoSubmitPackage for why we use
            # state_hash and not unexpanded_state_hash
            if parent_package.state_hash == devel_package.state_hash:
                continue

            if devel_package.project == self.conf.project:
                if str(parent_package) not in INTERNAL_LINK_DIFFERENT_HASH_SAFE:
                    print >>sys.stderr, 'Devel package %s (for %s) belongs to target project %s but state hash is different: this should never happen.' % (devel_package, parent_package, self.conf.project)
                continue

            hash_key = str(parent_package)
            if with_diff_hash.has_key(hash_key):
                print >>sys.stderr, '%s appearing twice as parent package.' % parent_package
                continue

            with_diff_hash[hash_key] = True

            self._packages_with_diff.append((devel_package, parent_package))

        self._packages_with_diff.sort()


    def _fetch_existing_requests(self):
        xml_root = fetch_requests_for_project(self.conf.apiurl, self.conf.project)

        self._submit_requests = {}
        self._delete_requests = {}

        for request_node in xml_root.findall('request'):
            request_id = request_node.get('id')
            if not request_id:
                print >>sys.stderr, 'Ignoring request with no request id.'
                continue

            for action_node in request_node.findall('action'):
                action_type = action_node.get('type')
                if not action_type:
                    print >>sys.stderr, 'Ignoring request %s: no action type.' % request_id
                    continue

                if action_type not in ('submit', 'delete'):
                    print >>sys.stderr, 'Ignoring request %s: action type \'%s\' not expected.' % (request_id, action_type)
                    continue

                source = None
                target = None

                source_node = action_node.find('source')
                if source_node is not None:
                    source = AutoSubmitPackage.from_request_node(source_node)
                target_node = action_node.find('target')
                if target_node is not None:
                    target = AutoSubmitPackage.from_request_node(target_node)

                if not target:
                    print >>sys.stderr, 'Ignoring request %s: target mis-defined.' % request_id
                    continue

                key = str(target)

                if action_type == 'submit':
                    if not source:
                        print >>sys.stderr, 'Ignoring submit request %s: source mis-defined.' % request_id
                        continue

                    new = (request_id, source)
                    if not self._submit_requests.has_key(key):
                        requests = [ new ]
                    else:
                        requests = self._submit_requests[key].append(new)
                    self._submit_requests[key] = requests
                elif action_type == 'delete':
                    if not self._delete_requests.has_key(key):
                        requests = [ request_id ]
                    else:
                        requests = self._delete_requests[key].append(key)
                    self._delete_requests[key] = requests


    def _devel_package_check_already_submitted(self, devel_package, parent_package):
        xml_root = fetch_all_requests_for_package(self.conf.apiurl, parent_package.project, parent_package.package)

        for request_node in xml_root.findall('request'):
            request_id = request_node.get('id')
            if not request_id:
#                raise AutoSubmitUnlikelyException('No access to cache database.' % self._dbfile)
                print >>sys.stderr, 'Ignoring request with no request id.'
                continue

            for action_node in request_node.findall('action'):
                action_type = action_node.get('type')
                if not action_type:
                    print >>sys.stderr, 'Ignoring request %s: no action type.' % request_id
                    continue

                if action_type not in ('submit',):
                    print >>sys.stderr, 'Ignoring request %s: action type \'%s\' not expected.' % (request_id, action_type)
                    continue

                source = None

                source_node = action_node.find('source')
                if source_node is not None:
                    source = AutoSubmitPackage.from_request_node(source_node)

                if not source:
                    print >>sys.stderr, 'Ignoring request %s: source mis-defined.' % request_id
                    continue

                if devel_package == source and devel_package.rev == source.rev:
                    return request_id

        return None


    def _auto_submit_enabled(self, package):
        ''' Checks if auto-submit is disabled for this package.

            By default, it's all enabled. But there might be some attribute in OBS
            to disable this.

            We first check if it's disabled for the project.
        '''
#TODO if there is an attribute, properly check for it, with some cache. Right now, we hardcode a blacklist...

        if package.project in [ 'GNOME:Factory', 'GNOME:Apps' ]:
            return False

        return True


    def _should_filter_package(self, devel_package, parent_package):
        ''' To know if we need to create a submit request, we check the
            following:
            a) Checks that do not require any network activity
               1) the current state of the devel package is not a state we've
                  already seen
               2) there is a diff in .changes between devel and parent
               3) the parent package has no deleterequest associated to it (we
                  have the list of requests already)
            b) Checks that do require network activity
               1) auto-submit is enabled for the devel package (or for the
                  whole devel project)
               2) state of the devel package we got via the status API is still
                  current; if no, go back to a) with up-to-date state.
                  We also fetch the rev from devel package at this point.
               3) there is an open submit request for this state in the devel
                  package (we have the list of requests already, but we need
                  data fetched in b.2.)
               4) there was a submit request (even if revoked,
                  superseded, etc.) with the same state in the devel package
                  (we need to fetch old submit requests for this package)

            Note: we cannot rely on state_hash here. There's no guarantee we'll
            still have a valid expanded hash anymore -- this can heppen if we
            re-enter this method after b.2.
        '''
        # a.1. Was already seen/handled in the past; this cache is not completely useless! ;-)
        (cached_devel_project, cached_devel_package, cached_devel_state_hash) = self._cache.get_from_cache(parent_package.project, parent_package.package)
        # See hash documentation in AutoSubmitPackage for why we use state_hash
        # and not unexpanded_state_hash
        if cached_devel_project == devel_package.project and cached_devel_package == devel_package.package and cached_devel_state_hash == devel_package.state_hash:
            self._verbose_print('Not submitting %s to %s: changes already seen in the past.' % (devel_package, parent_package))
            return True

        # a.2. The .changes files are the same, so not worth submitting.
        # (Ignored if the status API doesn't have the attributes for .changes hash)
        if parent_package.changes_hash and parent_package.changes_hash == devel_package.changes_hash:
            self._verbose_print('Not submitting %s to %s: .changes files are the same.' % (devel_package, parent_package))
            return True

        # a.3. The parent package is, apparently, scheduled to be deleted. If the delete request is rejected, we'll submit on next run anyway.
        if self._delete_requests.has_key(str(parent_package)):
            self._verbose_print('Not submitting %s to %s: delete request for %s filed.' % (devel_package, parent_package, parent_package))
            return True

        # b.1. Auto-submit is enabled for the devel package (or for the whole devel project)
        if not self._auto_submit_enabled(devel_package):
            self._verbose_print('Not submitting %s to %s: auto-submit disabled.' % (devel_package, parent_package))
            return True

        # b.2. State of the devel package we got via the status API is still current
        # This is also where we fetch rev, needed for the submit request. If we
        # have a rev, that means we've called that already.
        if not devel_package.rev:
            old_hash = devel_package.state_hash
            devel_package.fetch_latest_package_state(self.conf.apiurl)
            # See hash documentation in AutoSubmitPackage for why we use
            # state_hash and not unexpanded_state_hash
            if old_hash != devel_package.state_hash:
                # Devel package is more recent, let's check everything for the most recent version
                return self._should_filter_package(devel_package, parent_package)

        # b.3. There is already an open submit request; we need to see if this is for the current state of the source package.
        if self._submit_requests.has_key(str(parent_package)):
            old_sr = None
            requests = self._submit_requests[str(parent_package)]
            for (request_id, source) in requests:
                if devel_package != source:
                    continue

                if source.rev == devel_package.rev:
                    old_sr = request_id
                    break

            if old_sr is not None:
                self._verbose_print('Not submitting %s to %s: already submitted (%s).' % (devel_package, parent_package, old_sr))
                return True
            else:
                self._verbose_print('Should submit %s to %s with newer version.' % (devel_package, parent_package))

        # b.4. There was a submit request (even if revoked, superseded, etc.) with the same state in the devel package
        old_sr = self._devel_package_check_already_submitted(devel_package, parent_package)
        if old_sr is not None:
            self._verbose_print('Not submitting %s to %s: already submitted in the past (%s).' % (devel_package, parent_package, old_sr))
            return True

        if not parent_package.rev:
            old_hash = parent_package.state_hash
            parent_package.fetch_latest_package_state(self.conf.apiurl, nochanges = True)
            # See hash documentation in AutoSubmitPackage for why we use
            # state_hash and not unexpanded_state_hash
            if parent_package.state_hash ==  devel_package.state_hash:
                self._verbose_print('Not submitting %s to %s: status info out-of-date (parent package already the same).' % (devel_package, parent_package))
                return True

        return False


    def _do_auto_submit(self, devel_package, parent_package):
        if self.conf.debug:
            self._verbose_print('Pretending to submit %s to %s (debug mode)' % (devel_package, parent_package))
            return True

        self._verbose_print('Submitting %s to %s' % (devel_package, parent_package))
        try:
            id = create_submit_request(self.conf.apiurl, devel_package.project, devel_package.package, devel_package.rev, parent_package.project, parent_package.package)
            self._verbose_print('Submitted %s to %s: %s' % (devel_package, parent_package, id), level = 2)
            return True
        except Exception, e:
            print >>sys.stderr, 'Failed to submit %s to %s: %s' (devel_package, parent_package, e)
        return False


    def run(self):
        self._cache = AutoSubmitCache(self.conf)

        self._fetch_packages_with_diff()
        if self.conf.debug:
            print '#####################################################'
            print 'Packages with a diff (%d)' % len(self._packages_with_diff)
            print '#####################################################'
            for (devel_package, parent_package) in self._packages_with_diff:
                print '%s -> %s' % (str(devel_package), str(parent_package))
            print ''

        self._fetch_existing_requests()
        if self.conf.debug:
            print '#####################################################'
            print 'Packages already with a submission (%d)' % len(self._submit_requests)
            print '#####################################################'
            for (key, value) in self._submit_requests.items():
                output = [ 'from %s (%s)' % (str(source), request_id) for (request_id, source) in value ]
                print 'Requests to %s: %s' % (key, ','.join(output))
            print ''

            print '#####################################################'
            print 'Packages scheduled for deletion (%d)' % len(self._delete_requests)
            print '#####################################################'
            for (key, value) in self._delete_requests.items():
                print 'Delete requests for %s: %s' % (key, ','.join(value))
            print ''

            print '#####################################################'
            print 'Filtering and submitting'
            print '#####################################################'

        try:
            for (devel_package, parent_package) in self._packages_with_diff:
                update_cache = False

                try:
                    if self._should_filter_package(devel_package, parent_package):
                        update_cache = True
                        if self.conf.debug:
                            print 'Filtered %s -> %s' % (str(devel_package), str(parent_package))
                    else:
                        if self.conf.debug:
                            print 'Submitting %s -> %s' % (str(devel_package), str(parent_package))
                        if self._do_auto_submit(devel_package, parent_package):
                            update_cache = True
                except Exception, e:
                    print >>sys.stderr, 'Failed to deal with %s to %s: %s' % (devel_package, parent_package, e)

                if update_cache:
                    # See hash documentation in AutoSubmitPackage for why we
                    # use state_hash and not unexpanded_state_hash
                    self._cache.add_to_cache(parent_package.project, parent_package.package, devel_package.project, devel_package.package, devel_package.state_hash)

        except Exception, e:
            # We really, really, really want to commit the cache in all cases
            self._cache.commit()
            raise e
        finally:
            self._cache.commit()

        self._cache.prune_old_entries()

        del self._cache
        self._cache = None


#######################################################################


def lock_run(conf):
    # FIXME: this is racy, we need a real lock file. Or use an atomic operation
    # like mkdir instead
    running_file = os.path.join(conf.cache_dir, 'running')

    if os.path.exists(running_file):
        return False

    open(running_file, 'w').write('')

    return True


def unlock_run(conf):
    running_file = os.path.join(conf.cache_dir, 'running')

    os.unlink(running_file)


#######################################################################


def main(args):
    parser = optparse.OptionParser()

    parser.add_option('--cache-dir', dest='cache_dir',
                      help='cache directory (default: current directory)')
    parser.add_option('--apiurl', '-A', dest='apiurl', default='https://api.opensuse.org/',
                      help='build service API server (default: https://api.opensuse.org/)')
    parser.add_option('--project', '-p', dest='project', default='openSUSE:Factory',
                      help='target project to auto-submit to (default: openSUSE:Factory)')
    parser.add_option('--log', dest='log',
                      help='log file to use (default: stderr)')
    parser.add_option('--verbose', '-v', action='count',
                      default=0, dest='verbose',
                      help='be verbose; use multiple times to add more verbosity (default: false)')
    parser.add_option('--debug', action='store_true',
                      default=False, dest='debug',
                      help='add debug output and do not create real submit requests (default: false)')

    (options, args) = parser.parse_args()

    conf = AutoSubmitConfig(options)

    if options.log:
        path = os.path.realpath(options.log)
        safe_mkdir_p(os.path.dirname(path))
        sys.stderr = open(options.log, 'a')

    oscconf.get_config(override_apiurl = conf.apiurl)

    try:
        os.makedirs(conf.cache_dir)
    except OSError, e:
        if e.errno != errno.EEXIST:
            print >>sys.stderr, 'Cannot create cache directory: %s' % e
            return 1

    if not lock_run(conf):
        print >>sys.stderr, 'Another instance of the script is running.'
        return 1

    worker = AutoSubmitWorker(conf)

    retval = 1

    try:
        worker.run()
        retval = 0
    except Exception, e:
        if isinstance(e, (AutoSubmitException,)):
            print >>sys.stderr, e
        else:
            traceback.print_exc()

    unlock_run(conf)

    return retval


if __name__ == '__main__':
    try:
        ret = main(sys.argv)
        sys.exit(ret)
    except KeyboardInterrupt:
        pass
