#!/usr/bin/python
#
# Copyright (c) 2016, t-kenji
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the authors nor the names of its contributors
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

import os
import sys
import re
import itertools

from colorhash import ColorHash
from pkg_resources import resource_filename

from trac.config import (
    ConfigSection, Option
)
from trac.core import *
from trac.util.text import is_obfuscated
from trac.web.api import (
    IRequestFilter, ITemplateStreamFilter,
    arg_list_to_args, parse_arg_list
)
from trac.web.chrome import (
    Chrome, ITemplateProvider, add_stylesheet, web_context
)
from genshi.filters.transform import Transformer
from genshi.builder import tag


class KeywordLabelsModule(Component):

    implements(IRequestFilter,
               ITemplateProvider,
               ITemplateStreamFilter)

    ticketlink_query = Option('query', 'ticketlink_query',
        default='?status=!closed')

    keyword_labels_section = ConfigSection('keyword-labels',
        """In this section, you can define custom label colors.""")

    # IRequestFilter methods

    def pre_process_request(self, req, handler):
        return handler

    def post_process_request(self, req, template, data, content_type):
        path = req.path_info
        if path.startswith('/ticket/') or path.startswith('/newticket'):
            if data and 'ticket' in data:
                ticket = data['ticket']
                keywords = ticket['keywords'] or ''
                for field in data.get('fields', ''):
                    if field.get('name') == 'keywords':
                        from trac.ticket.query import QueryModule
                        if not (isinstance(keywords, basestring) and
                                self.env.is_component_enabled(QueryModule)):
                            break
                        context = web_context(req, ticket)
                        field['rendered'] = self._query_link_words(context, 'keywords', keywords, 'keyword-label ticket')
        return template, data, content_type

    # ITemplateProvider methods

    def get_htdocs_dirs(self):
        yield 'keyword_labels', resource_filename(__name__, 'htdocs')

    def get_templates_dirs(self):
        return []

    # ITemplateStreamFilter methods

    def filter_stream(self, req, method, filename, stream, data):
        if req.path_info.startswith('/report') or req.path_info.startswith('/query'):
            from trac.ticket.query import QueryModule
            from trac.ticket.model import Ticket
            if not (self.env.is_component_enabled(QueryModule)) \
               and 'tickets' not in data \
               and 'row_groups' not in data:
                return stream

            reported_tickets = []
            if 'tickets' in data:
                class_ = 'keyword-label query'

                for row in data['tickets']:
                    try:
                        ticket = Ticket(self.env, row['id'])
                    except KeyError:
                        continue
                    else:
                        reported_tickets.insert(0, ticket)
            elif 'row_groups' in data:
                class_ = 'keyword-label report'

                for group in data['row_groups']:
                    for row in group[1]:
                        try:
                            ticket = Ticket(self.env, row['resource'].id)
                        except KeyError:
                            continue
                        else:
                            reported_tickets.insert(0, ticket)

            def find_change(stream):
                ticket = reported_tickets.pop()
                keywords = ticket['keywords'] or ''
                context = web_context(req, ticket)
                tag_ = self._query_link_words(context, 'keywords', keywords, class_, prepend=[tag.span(' ')])
                return itertools.chain(stream[0:5], tag_, stream[6:])

            xpath = '//table[@class="listing tickets"]/tbody/tr/td[@class="summary"]'
            stream |= Transformer(xpath).filter(find_change)

        add_stylesheet(req, 'keyword_labels/css/keyword_labels.css')
        return stream

    # Inner methods

    def _query_link_words(self, context, name, value, class_, prepend=None, append=None):
        """Splits a list of words and makes a query link to each separately"""
        from trac.ticket.query import QueryModule
        if not (isinstance(value, basestring) and  # None or other non-splitable
                self.env.is_component_enabled(QueryModule)):
            return value
        args = arg_list_to_args(parse_arg_list(self.ticketlink_query))
        items = []
        if prepend:
            items.extend(prepend)
        for i, word in enumerate(re.split(r'([;,\s]+)', value)):
            if i % 2:
                items.append(' ')
            elif word:
                backgroundColor = self.keyword_labels_section.get(word.lower())
                fontColor = self.keyword_labels_section.get(word.lower() + '.font_color', 'white')
                if not backgroundColor:
                    backgroundColor = ColorHash(word.encode('utf-8')).hex
                styles = {
                    'backgroundColor': backgroundColor,
                    'fontColor': fontColor,
                }
                word_args = args.copy()
                word_args[name] = '~' + word
                items.append(tag.a(word,
                                   style='background-color: {backgroundColor}; color: {fontColor}'.format(**styles),
                                   class_=class_,
                                   href=context.href.query(word_args)))
        if append:
            items.extend(append)
        return tag(items)
