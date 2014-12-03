#!/usr/bin/env python
# pylint: disable=invalid-name
# this is a script, not a module
# pylint: enable=invalid-name

"""
Learn and predict dialogue acts from EDU feature vectors
"""

import argparse
import copy
import cPickle

from Orange.classification import Classifier
import Orange
import Orange.data
import Orange.data.io
import Orange.feature

from educe.stac.annotation import set_addressees
from educe.stac.learning.addressee import guess_addressees_for_edu
import educe.stac.learning.features as stac_features
import educe.stac
from educe.stac.util.output import save_document


# ---------------------------------------------------------------------
# arguments and main
# ---------------------------------------------------------------------


def predict_dialogue_act(model, vector):
    """
    Predict the dialogue act associated with a given feature vector
    """
    return model(vector, Classifier.GetValue)


def mk_instance(domain, vec):
    """
    Build an Orange instance from an extracted feature vector
    """

    def get_val(feat):
        "get the value associated with a feature"
        val_ = vec[feat.name]
        val = val_.encode('utf-8') if isinstance(val_, unicode) else val_
        if isinstance(feat, Orange.feature.Continuous):
            return val
        elif isinstance(feat, Orange.feature.Discrete):
            if str(val) in feat.values:
                return str(val)
            else:
                return '?'
        else:
            return val

    inst = Orange.data.Instance(domain, map(get_val, domain))
    for meta in domain.get_metas().values():
        inst[meta] = str(get_val(meta))

    return inst


def model_domain(model):
    """
    Return a slightly modified version of the domain for the
    given model, partly to work around faulty type detection
    for some of the fields.
    """
    # no class variable - we don't know it yet
    domain = Orange.data.Domain(model.domain.features, False)
    for i, meta in model.domain.get_metas().items():
        # coerce meta type to string because for some odd reason
        # Orange seems to learn the dialogues as discrete
        str_meta = Orange.feature.String(meta.name)
        domain.add_meta(i, str_meta)
    return domain


def _read_annotate_inputs(args):
    """
    Return a `FeaturesInput` and a model
    """
    args.experimental = True  # use parser, not sure if we want this
    args.ignore_cdus = False
    args.debug = False
    inputs = stac_features.read_corpus_inputs(args, 'unannotated')
    with open(args.model, "rb") as fstream:
        model = cPickle.load(fstream)
    return inputs, model


def _output_key(key):
    """
    Given a `FileId` key for an input document, return a version that
    would be appropriate for its output equivalent
    """
    key2 = copy.copy(key)
    key2.stage = 'units'
    key2.annotator = 'simple-da'
    return key2


def annotate_edu(model, domain, inputs, current, edu):
    """
    Modify an edu by guessing its dialogue act and addressee
    """
    vec = stac_features.SingleEduKeysForSingleExtraction(inputs)
    vec.fill(current, edu)
    instance = mk_instance(domain, vec)
    addressees = guess_addressees_for_edu(current.contexts,
                                          current.players,
                                          edu)
    edu.type = str(predict_dialogue_act(model, instance))
    set_addressees(edu, addressees)


def command_annotate(args):
    """
    Top-level command: given a dialogue act model, and a corpus with some
    Glozz documents, perform dialogue act annotation on them, and simple
    addressee detection, and dump Glozz documents in the output directory
    """
    inputs, model = _read_annotate_inputs(args)
    domain = model_domain(model)

    people = stac_features.get_players(inputs)

    # make predictions and save the output
    for k in inputs.corpus:
        doc = inputs.corpus[k]
        current = stac_features.mk_env(inputs, people, k, True).current
        edus = [unit for unit in doc.units if educe.stac.is_edu(unit)]
        for edu in edus:
            annotate_edu(model, domain, inputs, current, edu)
        save_document(args.output, _output_key(k), doc)


def main():
    "channel to subcommands"

    usage = "%(prog)s [options] data_file"
    psr = argparse.ArgumentParser(usage=usage)

    psr = argparse.ArgumentParser(add_help=False)
    psr.add_argument("corpus", default=None, metavar="DIR",
                     help="corpus to annotate (live mode assumed)")
    psr.add_argument('resources', metavar='DIR',
                     help='Resource dir (eg. data/resources/lexicon)')
    psr.add_argument("--model", default=None, required=True,
                     help="provide saved model for prediction of "
                     "dialogue acts")
    psr.add_argument("--output", "-o", metavar="DIR",
                     default=None,
                     required=True,
                     help="output directory")
    psr.set_defaults(func=command_annotate)

    args = psr.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()

# vim:filetype=python: