# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import json
import hashlib
from functools import wraps

from django.http import Http404
from django.template import RequestContext
from django.shortcuts import get_object_or_404, render_to_response
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import transaction
from django.contrib.gis.geos import Point, MultiPolygon, Polygon

from treemap.units import Convertible
from treemap.models import (Tree, Species, Instance, MapFeature,
                            MapFeaturePhoto)
from treemap.util import (package_validation_errors,
                          bad_request_json_response, to_object_name)

from treemap.images import get_image_from_request
from treemap.lib.photo import context_dict_for_photo
from treemap.lib.map_feature import (get_map_feature_or_404,
                                     context_dict_for_plot,
                                     context_dict_for_resource,
                                     context_dict_for_map_feature)


def _request_to_update_map_feature(request, instance, feature):
    try:
        request_dict = json.loads(request.body)
        feature, tree = update_map_feature(request_dict, request.user, feature)

        # We need to reload the instance here since a new georev
        # may have been set
        instance = Instance.objects.get(pk=instance.pk)

        return {
            'ok': True,
            'geoRevHash': instance.geo_rev_hash,
            'featureId': feature.id,
            'treeId': tree.id if tree else None,
            'enabled': instance.feature_enabled('add_plot')
        }
    except ValidationError as ve:
        return bad_request_json_response(
            validation_error_dict=ve.message_dict)


def _add_map_feature_photo_helper(request, instance, feature_id):
    feature = get_map_feature_or_404(feature_id, instance)
    data = get_image_from_request(request)
    return feature.add_photo(data, request.user)


def get_photo_context_and_errors(fn):
    @wraps(fn)
    def wrapper(request, instance, feature_id, *args, **kwargs):
        error = None
        try:
            fn(request, instance, feature_id, *args, **kwargs)
        except ValidationError as e:
            error = '; '.join(e.messages)
        feature = get_map_feature_or_404(feature_id, instance)
        photos = feature.photos()
        return {'photos': map(context_dict_for_photo, photos),
                'error': error}

    return wrapper


def map_feature_detail(request, instance, feature_id, render=False):
    feature = get_map_feature_or_404(feature_id, instance)

    ctx_fn = (context_dict_for_plot if feature.is_plot
              else context_dict_for_resource)
    context = ctx_fn(request, feature)

    if render:
        if feature.is_plot:
            template = 'treemap/plot_detail.html'
        else:
            template = 'map_features/%s_detail.html' % feature.feature_type
        return render_to_response(template, context, RequestContext(request))
    else:
        return context


def render_map_feature_detail(*args, **kwargs):
    return map_feature_detail(*args, render=True, **kwargs)


def plot_detail(request, instance, feature_id, edit=False, tree_id=None):
    feature = get_map_feature_or_404(feature_id, instance, 'Plot')
    return context_dict_for_plot(request, feature, edit, tree_id)


def render_map_feature_add(request, instance, type):
    if type in instance.map_feature_types[1:]:
        template = 'map_features/%s_add.html' % type
        return render_to_response(template, None, RequestContext(request))
    else:
        raise Http404('Instance does not support feature type ' + type)


def add_map_feature(request, instance, type='Plot'):
    feature = MapFeature.create(type, instance)
    return _request_to_update_map_feature(request, instance, feature)


def update_map_feature_detail(request, instance, feature_id, type='Plot'):
    feature = get_map_feature_or_404(feature_id, instance, type)
    return _request_to_update_map_feature(request, instance, feature)


def delete_map_feature(request, instance, feature_id, type='Plot'):
    feature = get_map_feature_or_404(feature_id, instance, type)
    try:
        feature.delete_with_user(request.user)
        return {'ok': True}
    except ValidationError as ve:
        return "; ".join(ve.messages)


@transaction.commit_on_success
def update_map_feature(request_dict, user, feature):
    """
    Update a map feature. Expects JSON in the request body to be:
    {'model.field', ...}

    Where model is either 'tree', 'plot', or another map feature type
    and field is any field on the model.
    UDF fields should be prefixed with 'udf:'.

    This method can be used to create a new map feature by passing in
    an empty MapFeature object (i.e. Plot(instance=instance))
    """
    feature_object_names = [to_object_name(ft)
                            for ft in feature.instance.map_feature_types]

    if isinstance(feature, Convertible):
        # We're going to always work in display units here
        feature.convert_to_display_units()

    def split_model_or_raise(identifier):
        parts = identifier.split('.', 1)

        if (len(parts) != 2 or
                parts[0] not in feature_object_names + ['tree']):
            raise Exception(
                'Malformed request - invalid field %s' % identifier)
        else:
            return parts

    def set_attr_on_model(model, attr, val):
        field_classname = \
            model._meta.get_field_by_name(attr)[0].__class__.__name__

        if field_classname.endswith('PointField'):
            srid = val.get('srid', 3857)
            val = Point(val['x'], val['y'], srid=srid)
            val.transform(3857)
        elif field_classname.endswith('MultiPolygonField'):
            srid = val.get('srid', 4326)
            val = MultiPolygon(Polygon(val['polygon'], srid=srid), srid=srid)
            val.transform(3857)

        if attr == 'mapfeature_ptr':
            if model.mapfeature_ptr_id != value:
                raise Exception(
                    'You may not change the mapfeature_ptr_id')
        elif attr == 'id':
            if val != model.pk:
                raise Exception("Can't update id attribute")
        elif attr.startswith('udf:'):
            udf_name = attr[4:]

            if udf_name in [field.name
                            for field
                            in model.get_user_defined_fields()]:
                model.udfs[udf_name] = val
            else:
                raise KeyError('Invalid UDF %s' % attr)
        elif attr in model.fields():
            model.apply_change(attr, val)
        else:
            raise Exception('Malformed request - invalid field %s' % attr)

    def save_and_return_errors(thing, user):
        try:
            if isinstance(thing, Convertible):
                thing.convert_to_database_units()

            thing.save_with_user(user)
            return {}
        except ValidationError as e:
            return package_validation_errors(thing._model_name, e)

    tree = None

    for (identifier, value) in request_dict.iteritems():
        object_name, field = split_model_or_raise(identifier)

        if object_name in feature_object_names:
            model = feature
        elif object_name == 'tree' and feature.feature_type == 'Plot':
            # Get the tree or spawn a new one if needed
            tree = (tree or
                    feature.current_tree() or
                    Tree(instance=feature.instance))

            # We always edit in display units
            tree.convert_to_display_units()

            model = tree
            if field == 'species' and value:
                value = get_object_or_404(Species,
                                          instance=feature.instance, pk=value)
            elif field == 'plot' and value == unicode(feature.pk):
                value = feature
        else:
            raise Exception(
                'Malformed request - invalid model %s' % object_name)

        set_attr_on_model(model, field, value)

    errors = {}

    if feature.fields_were_updated():
        errors.update(save_and_return_errors(feature, user))
    if tree and tree.fields_were_updated():
        tree.plot = feature
        errors.update(save_and_return_errors(tree, user))

    if errors:
        raise ValidationError(errors)

    # Refresh feature.instance in case geo_rev_hash was updated
    feature.instance = Instance.objects.get(id=feature.instance.id)

    return feature, tree


def map_feature_hash(request, instance, feature_id, edit=False, tree_id=None):
    """
    Compute a unique hash for a given plot or tree

    tree_id is ignored since trees are included as a
    subset of the plot's hash. It is present here because
    this function is wrapped around views that can take
    tree_id as an argument
    """

    InstanceMapFeature = instance.scope_model(MapFeature)
    base = get_object_or_404(InstanceMapFeature, pk=feature_id).hash

    if request.user:
        pk = request.user.pk or ''

    return hashlib.md5(base + ':' + str(pk)).hexdigest()


@get_photo_context_and_errors
def add_map_feature_photo(request, instance, feature_id):
    _add_map_feature_photo_helper(request, instance, feature_id)


@get_photo_context_and_errors
def rotate_map_feature_photo(request, instance, feature_id, photo_id):
    orientation = request.REQUEST.get('degrees', None)
    if orientation not in {'90', '180', '270', '-90', '-180', '-270'}:
        raise ValidationError('"degrees" must be a multiple of 90°')

    degrees = int(orientation)
    mf_photo = get_object_or_404(MapFeaturePhoto, pk=photo_id)

    image_data = mf_photo.image.read(settings.MAXIMUM_IMAGE_SIZE)
    mf_photo.set_image(image_data, degrees_to_rotate=degrees)
    mf_photo.save_with_user(request.user)


def map_feature_popup(request, instance, feature_id):
    feature = get_map_feature_or_404(feature_id, instance)
    context = context_dict_for_map_feature(request, feature)
    return context
