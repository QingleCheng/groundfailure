import os
from mapio.shake import ShakeGrid
from configobj import ConfigObj
from groundfailure.logisticmodel import LogisticModel
from groundfailure.conf import correct_config_filepaths
from groundfailure.makemaps import parseConfigLayers, parseMapConfig
from groundfailure import makemaps
from groundfailure.assessmodels import concatenateModels as concM
from groundfailure.assessmodels import computeHagg
#from groundfailure.newmark import godt2008
import numpy as np
from impactutils.io.cmd import get_command_output
from shutil import copy
from datetime import datetime
import re
import html

def makeWebpage(maplayerlist, configs, web_template, shakemap, outfolder=None, includeunc=False,
                cleanup=False):
    """
    :param maplayers: list of maplayer outputs from multiple models
    TODO add in logic to deal with when one of the model types is missing
    """
    # get ShakeMap id
    sm_id = maplayerlist[0]['model']['description']['shakemap']
    if outfolder is None:
        outfolder = os.getcwd()

    fullout = os.path.join(outfolder, sm_id)
    content = os.path.join(fullout, 'content')
    articles = os.path.join(content, 'articles')
    hidden_pages = os.path.join(content, 'hidden_pages')
    pages = os.path.join(content, 'pages')
    images = os.path.join(content, 'images')
    #images1 = os.path.join(images, sm_id)
    theme = os.path.join(web_template, 'theme')
    #static = os.path.join(fullout, 'output', 'static')
    try:
        os.mkdir(fullout)
    except Exception as e:
        print(e)
    try:
        os.mkdir(content)
    except Exception as e:
        print(e)
    try:
        os.mkdir(images)
    except Exception as e:
        print(e)
    try:
        os.mkdir(pages)
    except Exception as e:
        print(e)
    try:
        os.mkdir(articles)
    except Exception as e:
        print(e)

    peliconf = os.path.join(fullout, 'pelicanconf.py')
    copy(os.path.join(web_template, 'pelicanconf.py'), peliconf)

    # Separate the LS and LQ models
    LS = []
    LQ = []
    confLS = []
    confLQ = []
    for conf, maplayer in zip(configs, maplayerlist):
        if 'landslide' in maplayer['model']['description']['parameters']['modeltype'].lower():
            LS.append(maplayer)
            confLS.append(conf)
        elif 'liquefaction' in maplayer['model']['description']['parameters']['modeltype'].lower():
            LQ.append(maplayer)
            confLQ.append(conf)
        else:
            raise Exception("model type is undefined, check maplayer['model']['parameters']['modeltype'] to ensure it is defined")

    if len(LS) > 0:
        HaggLS = []
        maxLS = []
        logLS = []
        limLS = []
        colLS = []
        maskLS = []
        namesLS = []

        for conf, L in zip(confLS, LS):
            #TODO add threshold option for Hagg
            HaggLS.append(computeHagg(L['model']['grid']))
            maxLS.append(np.nanmax(L['model']['grid'].getData()))
            plotorder, logscale, lims, colormaps, maskthreshes = parseConfigLayers(L, conf, keys=['model'])
            logLS.append(logscale[0])
            limLS.append(lims[0])
            colLS.append(colormaps[0])
            #maskLS.append(maskthreshes[0])
            namesLS.append(L['model']['description']['name'])

        mapLS, filenameLS = makemaps.interactiveMap(concM(LS, astitle='model', includeunc=includeunc),
                                                    colormaps=colLS, lims=limLS, clear_zero=False,
                                                    logscale=logLS, separate=False, outfilename='LS_%s' % sm_id,
                                                    mapid='LS', savefiles=True, outputdir=images,
                                                    sepcolorbar=True, floatcb=False)
        write_individual(HaggLS, maxLS, namesLS, articles, 'Landslides',
                         interactivehtml=filenameLS[0], map1=mapLS)

    if len(LQ) > 0:
        HaggLQ = []
        maxLQ = []
        logLQ = []
        limLQ = []
        colLQ = []
        #maskLQ = []
        namesLQ = []

        for conf, L in zip(confLQ, LQ):
            HaggLQ.append(computeHagg(L['model']['grid']))
            maxLQ.append(np.nanmax(L['model']['grid'].getData()))
            plotorder, logscale, lims, colormaps, maskthreshes = parseConfigLayers(L, conf, keys=['model'])
            logLQ.append(logscale[0])
            limLQ.append(lims[0])
            colLQ.append(colormaps[0])
            #maskLQ.append(maskthreshes[0])
            namesLQ.append(L['model']['description']['name'])
        mapLQ, filenameLQ = makemaps.interactiveMap(concM(LQ, astitle='model', includeunc=includeunc),
                                                    colormaps=colLQ, lims=limLQ, clear_zero=False,
                                                    logscale=logLQ, separate=False, outfilename='LQ_%s' % sm_id,
                                                    savefiles=True, mapid='LQ', outputdir=images,
                                                    sepcolorbar=True, floatcb=False)

        write_individual(HaggLQ, maxLQ, namesLQ, articles, 'Liquefaction',
                         interactivehtml=filenameLQ[0], map1=mapLQ)

    #write_scibackground(LS, LQ)
    statement = get_statement(HaggLS, HaggLQ)
    write_summary(shakemap, pages, statement=statement)

    # run website
    retcode, stdout, stderr = get_command_output(('pelican -s %s -o %s -t %s') %
                                                (peliconf, os.path.join(fullout, 'output'), theme))
    print(stderr)
    #write_static_map(filenameLS, filenameLQ, static)

    if cleanup:
        #delete the content folder
        pass

    return fullout


def write_individual(Hagg, maxprobs, modelnames, outputdir, modeltype,
                     topimage=None, staticmap=None, map1=None, interactivehtml=None):
    """
    write markdown file for landslides or liquefaction
    """
    if modeltype == 'Landslides':
        id1= 'LS'
    else:
        id1 = 'LQ'
    # If single model and not in list form, turn into lists
    if type(Hagg) is float:
        Hagg = [Hagg]
        maxprobs = [maxprobs]
        modelnames = [modelnames]

    with open(os.path.join(outputdir, modeltype + '.md'), 'w') as file1:
        file1.write('title: %s\n' % modeltype.title())
        file1.write('date: %s\n' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        file1.write('<center><h2>%s</h2></center>' % modeltype.title())
        if topimage is not None:
            file1.write('  <img src="/images/%s" width="300" />\n' % topimage)
        if interactivehtml is not None:
            fileloc = interactivehtml.split('images')[-1]
            file1.write('    <center><a href="images%s">Click here for full interactive map</a></center>\n'
                        % fileloc)
            #if map1 is not None:
            #    with open(interactivehtml) as f:                
            #        js = re.findall('(?si)<script>(.*?)</script>', f.read())
            #    file1.write('<script>\n')
            #    #for line in js:
            #    file1.write(html.unescape(js[-1]))
            #    file1.write('\n</script>\n')
            #    file1.write('<center><div class="folium-map" id="map_%s"></div></center>' % map1._id)
            #else:
            file1.write('    <center><object id=%s, type="text/html" data=images%s height=500 width=500></object></center>\n'
                        % (modeltype, fileloc))
            
            cbname = fileloc.split('.html')[0] + '_colorbar' + '.png'
            file1.write('    <center><img src="images%s" width="300" href="images%s"/></center>\n' %
                        (cbname, cbname))
        if staticmap is not None:
            #file1.write('<center> <h2>Static Map<h2> </center>\n')
            file1.write('    <center><img src="images%s" width="450" href="images%s"/></center>\n' %
                        (staticmap.split('images')[-1], staticmap.split('images')[-1]))
                        
        file1.write('<hr>\n')
        file1.write('<center><h3>Summary</h3></center>')
        file1.write('<table style="width:100%">')
        file1.write('<tr><th>Model</th><th>Aggregate Hazard</th><th>Max. Probability</th></tr>\n')
        for H, m, n in zip(Hagg, maxprobs, modelnames):
            file1.write('<tr><td>%s</td><td>%0.2f km<sup>2</sup></td><td>%0.2f</td></tr>\n' % (n.title(), H, m))
        file1.write('</table>')



def write_static_map(filenameLS, filenameLQ, static):
    pass


def write_scibackground(configLS, configLQ):
    """
    write markdown file describing model background and references
    """
    pass


def write_summary(shakemap, outputdir, statement):
    edict = ShakeGrid.load(shakemap, adjust='res').getEventDict()
    temp = ShakeGrid.load(shakemap, adjust='res').getShakeDict()
    edict['eventid'] = temp['shakemap_id']
    edict['version'] = temp['shakemap_version']

    with open(os.path.join(outputdir, 'Summary.md'), 'w') as file1:
        file1.write('title: summary\n')
        file1.write('date: 2017-06-09\n')
        file1.write('modified: 2017-06-09\n')
        file1.write('# Ground failure\n')
        file1.write('### Last updated at: %s (UTC)\n' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        file1.write('### Based on ground motion estimates from ShakeMap version %1.1f\n' % edict['version'])
        file1.write('## Magnitude %1.1f - %s\n' % (edict['magnitude'], edict['event_description']))
        file1.write('### %s (UTC) | %1.4f°,  %1.4f° | %1.1f km\n' %
                    (edict['event_timestamp'].strftime('%Y-%m-%dT%H:%M:%S'), edict['lat'],
                     edict['lon'], edict['depth']))

        file1.write('### Summary\n')
        file1.write(statement)
        file1.write('<hr>')


def get_statement(HaggLS=None, HaggLQ=None):
    """
    get standardized statement based on Hagg of landslides and liquefaction
    """
    return 'Some automatically produced statement about the levels of landslide and liquefaction hazard relative to other historical events'
