import ee
ee.Initialize()
from ee.batch import Export
import sys

'''
Generates 10-day IRECI composites from cloud-masked Sentinel-2 imagery for a given Sentinel-2 tile and saves them to a Google Drive folder.
'''

# list of Sentinel-2 tiles you wish to download
tiles = ['16UEU', '16UFU', '16UGU']

for TILE in tiles:

    print(f"--- {TILE} ---", flush = True)

    CLOUD_COVER_THD = 70
    DRIVE_FOLDER = f"S2_{TILE}"
    NDAY = 10


    def maskS2clouds(image):
        qa = image.select('QA60')
        scl = image.select('SCL')
        cloudBitMask = 1 << 10
        cirrusBitMask = 1 << 11
        mask = qa.bitwiseAnd(cloudBitMask).eq(0).And(qa.bitwiseAnd(cirrusBitMask).eq(0))
        snowmask = scl.neq(11)
        return image.updateMask(mask).updateMask(snowmask).divide(10000).copyProperties(image).set({'system:time_start': image.get('system:time_start')})

    def calc_ireci(image):
        # (B7 − B4)/(B5/B6)
        ireciExpression = "(RE3 - R) / (RE1 / RE2) * 10000"
        bandDefs = {
        'RE3': image.select('B7'),
        'R': image.select('B4'),
        'RE1': image.select('B5'),
        'RE2': image.select('B6')
        }
        ireci = image.expression(ireciExpression, bandDefs).rename("IRECI")
        ireci = ireci.updateMask(ireci.lt(32767)).updateMask(ireci.gt(-32768))
        return ireci.copyProperties(image).set({'system:time_start': image.get('system:time_start')})


    filters = [
        ee.Filter.lt("CLOUD_COVERAGE_ASSESSMENT", CLOUD_COVER_THD),
        ee.Filter.equals("MGRS_TILE", TILE)
    ]

    ireci = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filter(filters).map(maskS2clouds).map(calc_ireci)
    crs = ee.String(ireci.first().projection().crs()).getInfo()
    region = ee.Image(ireci.first()).geometry()

    def createComposite(d):
        startDOY = ee.Number(d)
        endDOY = startDOY.add(NDAY)
        comp = ireci.filter(ee.Filter.dayOfYear(startDOY, endDOY))
        count = comp.count()
        index = ee.String("IRECI_").cat(startDOY.format("%03d"))
        medVI = comp.median()
        nullImage = ee.Image(-32768)
        res = ee.Image(ee.Algorithms.If(count.eq(0), nullImage, medVI)).set({'system:index': index})
        return(medVI)

    for i in range(1, 367, NDAY):
        bandName = f"IRECI_{TILE}_{NDAY}day_{i:03d}"
        exportImage = createComposite(i).rename(bandName)
        task = Export.image.toDrive(**{
            'image': exportImage,
            'scale': 20,
            'region': region,
            'crs': crs,
            'folder': DRIVE_FOLDER,
            'description': bandName,
            'fileNamePrefix': bandName
            })
        
        task.start()
