# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

from functools import partial

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import etag

from opentreemap.util import route, decorate as do

from treemap.decorators import (json_api_call, render_template, login_or_401,
                                require_http_method, string_to_response,
                                requires_feature,
                                creates_instance_user, instance_request,
                                username_matches_request_user,
                                admin_instance_request)

from treemap.views.user import (forgot_username, upload_user_photo,
                                user_audits, update_user, user,
                                instance_user, profile_to_user,
                                instance_user_audits)

from treemap.views.photo import (next_photo, photo_review,
                                 approve_or_reject_photo)

from treemap.views.tree import (add_tree_photo, tree_detail,
                                delete_tree, search_tree_benefits,
                                search_hash)

from treemap.views.misc import (edits, get_map_view_context, static_page,
                                boundary_to_geojson, boundary_autocomplete,
                                species_list, compile_scss, index)

from treemap.views.map_feature import (render_map_feature_detail,
                                       render_map_feature_add,
                                       update_map_feature_detail,
                                       map_feature_detail,
                                       plot_detail,
                                       delete_map_feature,
                                       map_feature_popup,
                                       add_map_feature,
                                       map_feature_hash,
                                       rotate_map_feature_photo,
                                       add_map_feature_photo)


add_map_feature_photo_do = partial(
    do,
    require_http_method("POST"),
    login_or_401,
    instance_request,
    creates_instance_user,
    render_template('treemap/partials/photo_carousel.html'))

#####################################
# misc content views
#####################################

edits_view = do(
    instance_request,
    requires_feature('recent_edits_report'),
    render_template('treemap/edits.html'),
    edits)

index_view = instance_request(index)

map_view = do(
    instance_request,
    render_template('treemap/map.html'),
    get_map_view_context)

static_page_view = do(
    instance_request,
    render_template('treemap/staticpage.html'),
    static_page)

instance_not_available_view = render_template(
    'treemap/instance_not_available.html')()

landing_view = render_template('base.html')()

unsupported_view = render_template('treemap/unsupported.html')()

error_404_view = render_template('404.html')(statuscode=404)
error_500_view = render_template('500.html')(statuscode=500)
error_503_view = render_template('503.html')(statuscode=503)

#####################################
# utility views
#####################################

root_settings_js_view = render_template('treemap/settings.js')(
    {'BING_API_KEY':
     settings.BING_API_KEY},
    mimetype='application/javascript')

instance_settings_js_view = instance_request(root_settings_js_view)

boundary_to_geojson_view = do(
    json_api_call,
    instance_request,
    boundary_to_geojson)

boundary_autocomplete_view = do(
    json_api_call,
    instance_request,
    boundary_autocomplete)

species_list_view = do(
    json_api_call,
    instance_request,
    species_list)

scss_view = do(
    require_http_method("GET"),
    string_to_response("text/css"),
    compile_scss)

#####################################
# mapfeature
#####################################

map_feature_add_view = do(
    instance_request,
    route(
        GET=render_map_feature_add,
        POST=do(
            login_or_401,
            json_api_call,
            creates_instance_user,
            add_map_feature)))

map_feature_detail_view = do(
    instance_request,
    route(
        GET=render_map_feature_detail,
        ELSE=do(
            login_or_401,
            json_api_call,
            creates_instance_user,
            route(
                PUT=update_map_feature_detail,
                DELETE=delete_map_feature))))

map_feature_accordion_view = do(
    instance_request,
    render_template('treemap/partials/map_feature_accordion.html'),
    map_feature_detail)

get_map_feature_sidebar_view = do(
    instance_request,
    etag(map_feature_hash),
    render_template('treemap/partials/sidebar.html'),
    map_feature_detail)

map_feature_popup_view = do(
    instance_request,
    etag(map_feature_hash),
    render_template('treemap/partials/map_feature_popup.html'),
    map_feature_popup)

add_map_feature_photo_endpoint = add_map_feature_photo_do(
    add_map_feature_photo)

rotate_map_feature_photo_endpoint = add_map_feature_photo_do(
    rotate_map_feature_photo)


#####################################
# plot
#####################################

edit_plot_detail_view = do(
    login_required,
    instance_request,
    creates_instance_user,
    render_template('treemap/plot_detail.html'),
    plot_detail)

get_plot_eco_view = do(
    instance_request,
    etag(map_feature_hash),
    render_template('treemap/partials/plot_eco.html'),
    plot_detail)


#####################################
# tree
#####################################

delete_tree_view = do(
    login_or_401,
    json_api_call,
    instance_request,
    creates_instance_user,
    delete_tree)

tree_detail_view = instance_request(tree_detail)

search_tree_benefits_view = do(
    instance_request,
    etag(search_hash),
    render_template('treemap/partials/eco_benefits.html'),
    search_tree_benefits)

add_tree_photo_endpoint = add_map_feature_photo_do(add_tree_photo)

#####################################
# user
#####################################

user_view = render_template('treemap/user.html')(user)

instance_user_view = instance_user

instance_user_audits_view = instance_user_audits

profile_to_user_view = profile_to_user

update_user_view = do(
    require_http_method("PUT"),
    username_matches_request_user,
    json_api_call,
    update_user)

user_audits_view = do(
    render_template('treemap/recent_user_edits.html'),
    user_audits)

upload_user_photo_view = do(
    require_http_method("POST"),
    username_matches_request_user,
    json_api_call,
    upload_user_photo)

forgot_username_view = route(
    GET=render_template('treemap/forgot_username.html')(),
    POST=do(
        render_template('treemap/forgot_username_done.html'),
        forgot_username))

#####################################
# photo
#####################################

photo_review_endpoint = do(
    require_http_method("GET"),
    admin_instance_request,
    render_template('treemap/photo_review.html'),
    photo_review)

photo_review_partial_endpoint = do(
    require_http_method("GET"),
    admin_instance_request,
    render_template('treemap/partials/photo_review.html'),
    photo_review)

next_photo_endpoint = do(
    require_http_method("GET"),
    admin_instance_request,
    render_template('treemap/partials/photo.html'),
    next_photo)

approve_or_reject_photo_view = do(
    require_http_method("POST"),
    admin_instance_request,
    approve_or_reject_photo)
