# Author: Eric Kow
# License: CeCILL-B (French BSD3-like)

"""
Split an EDU along given cut points
"""

from __future__ import print_function
import collections
import copy
import sys

import educe.annotation
import educe.stac
from educe.annotation import Span
from stac.edu import EnclosureGraph, sorted_first_widest

from stac.util.annotate import show_diff
from stac.util.glozz import\
    TimestampCache, set_anno_author, set_anno_date,\
    anno_id_from_tuple
from stac.util.args import\
    add_usual_input_args, add_usual_output_args,\
    read_corpus_with_unannotated,\
    get_output_dir, announce_output_dir,\
    comma_span
from stac.util.doc import narrow_to_span
from stac.util.output import save_document


NAME = 'split-edu'
_AUTHOR = 'stacutil'


def config_argparser(parser):
    """
    Subcommand flags.

    You should create and pass in the subparser to which the flags
    are to be added.
    """
    add_usual_input_args(parser, doc_subdoc_required=True)
    parser.add_argument('--annotator', metavar='PY_REGEX',
                        help='annotator')
    parser.add_argument('--spans', metavar='SPAN', type=comma_span,
                        nargs='+',
                        help='Desired output spans (must cover original EDU)')
    add_usual_output_args(parser)
    parser.set_defaults(func=main)


def _enclosing_span(spans):
    if len(spans) < 1:
        raise ValueError("must have at least one span")

    return Span(min(x.char_start for x in spans),
                max(x.char_end for x in spans))


def _tweak_presplit(tcache, doc, spans):
    """
    What to do in case the split was already done manually
    (in the discourse section)
    """
    new_edus = {}
    for span in sorted(spans):
        matches = [x for x in doc.units
                   if x.text_span() == span and educe.stac.is_edu(x)]
        if not matches:
            raise Exception("No matches found for %s in %s" %
                            (span, k), file=sys.stderr)
        edu = matches[0]
        set_anno_date(edu, tcache.get(span))
        set_anno_author(edu, _AUTHOR)


def _actually_split(tcache, doc, spans, edu):
    """
    Split the EDU, trying to generate the same new ID for the
    same new EDU across all sections

    Discourse stage: If the EDU is in any relations or CDUs,
    replace any references to it with a new CDU encompassing
    the newly created EDUs
    """

    new_edus = {}
    for span in sorted(spans):
        stamp = tcache.get(span)
        edu2 = copy.deepcopy(edu)
        new_id = anno_id_from_tuple((_AUTHOR, stamp))
        set_anno_date(edu2, stamp)
        set_anno_author(edu2, _AUTHOR)
        if doc.origin.stage == 'units':
            edu2.type = 'FIXME:' + edu2.type
            for key in edu2.features:
                edu2.features[key] = 'FIXME:' + edu2.features[key]
        new_edus[new_id] = edu2
        edu2.span = span
        doc.units.append(edu2)

    cdu_stamp = tcache.get(_enclosing_span(spans))
    cdu = educe.annotation.Schema(anno_id_from_tuple((_AUTHOR, cdu_stamp)),
                                  frozenset(new_edus),
                                  frozenset(),
                                  frozenset(),
                                  'Complex_discourse_unit',
                                  {'author': _AUTHOR,
                                   'creation-date': cdu_stamp},
                                  metadata={})
    cdu.fleshout(new_edus)

    want_cdu = False
    for rel in doc.relations:
        if rel.span.t1 == edu.local_id():
            want_cdu = True
            rel.span.t1 = cdu.local_id()
            rel.source = cdu
        if rel.span.t2 == edu.local_id():
            rel.span.t2 = cdu.local_id()
            rel.target = cdu
            want_cdu = True
    for schema in doc.schemas:
        if edu.local_id() in schema.units:
            schema.units = set(schema.units)
            schema.units.remove(edu.local_id())
            schema.units.add(cdu.local_id())
            want_cdu = True

    doc.units.remove(edu)
    if want_cdu:
        doc.schemas.append(cdu)


def _split_edu(tcache, k, doc, spans):
    """
    Find the edu covered by these spans and do the split
    """
    # seek edu
    big_span = _enclosing_span(spans)
    matches = [x for x in doc.units
               if x.text_span() == big_span and educe.stac.is_edu(x)]
    if not matches and k.stage != 'discourse':
        print("No matches found in %s" % k, file=sys.stderr)
    elif not matches:
        _tweak_presplit(tcache, doc, spans)
    else:
        _actually_split(tcache, doc, spans, matches[0])


def _mini_diff(k, old_doc, new_doc, span):
    """
    Return lines of text to be printed out, showing how the EDU
    split affected the text
    """
    mini_old_doc = narrow_to_span(old_doc, span)
    mini_new_doc = narrow_to_span(new_doc, span)
    return ["======= SPLIT EDU %s ========" % (k),
            "...",
            show_diff(mini_old_doc, mini_new_doc),
            "...",
            ""]


def main(args):
    """
    Subcommand main.

    You shouldn't need to call this yourself if you're using
    `config_argparser`
    """
    corpus = read_corpus_with_unannotated(args)
    postags = educe.stac.postag.read_tags(corpus, args.corpus)
    tcache = TimestampCache()
    output_dir = get_output_dir(args)
    for k in corpus:
        old_doc = corpus[k]
        new_doc = copy.deepcopy(old_doc)
        span = _enclosing_span(args.spans)
        _split_edu(tcache, k, new_doc, args.spans)
        diffs = _mini_diff(k, old_doc, new_doc, span)
        print("\n".join(diffs).encode('utf-8'), file=sys.stderr)
        save_document(output_dir, k, new_doc)
    announce_output_dir(output_dir)