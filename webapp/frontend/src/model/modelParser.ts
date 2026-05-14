import {Category, Detection, FloatRegion, ImageInfo, Kind, Prediction, Source, Taxon} from "./model.ts";


export function parseJsonImage(obj: any): ImageInfo {
    let image = new ImageInfo()
    image.filename = obj.filename
    image.taken_at = obj.taken_at
    image.failures = obj.failures
    image.timestamp = obj.timestamp
    image.prediction = parsePrediction(obj)
    image.detections = parseDetections(obj.detections, image)
    return image
}

function parsePrediction(prediction: any): Prediction {
    let result: Prediction = new Prediction()
    result.score = prediction.prediction_score
    result.model_version = prediction.model_version
    result.classification = parseKind(prediction.prediction)
    result.category = prediction.category
    result.country = prediction.country
    result.source = prediction.source as Source
    let taxa: Kind[] = prediction.classifications.classes.map(parseKind)
    result.top5 = new Map<Kind, number>()
    for(const [index, kind] of taxa.entries()) {
        result.top5.set(kind, prediction.classifications.scores[index])
    }

    return result
}

function parseDetections(detections: any[], image: ImageInfo): Detection[] {
    return detections.map((d)=>parseDetection(d,image)).sort((da, db)=>db.confidence - da.confidence)
}

function parseDetection(detection: any, image: ImageInfo): Detection{
    let result: Detection = new Detection()
    result.category = Category[detection.category]
    result.confidence = detection.conf
    if(image.prediction.species() && result.category == Category.ANIMAL )
        result.classification = image.prediction.species()
    // @ts-ignore this will always be 4 floats per SpeciesNet
    result.bbox = new FloatRegion(... detection.bbox)
    result.parent = image
    result.manual = false
    return result
}

function parseBBox(box: [number, number, number, number]): FloatRegion{
    let result
    return result
}

export function parseKind(kind: string): Kind {
    if(Category.contains(kind)) {
        return kind.toLowerCase() as Category
    } else {
        const tokens: string[] = kind.split(';')
        if(tokens.length == 7 && Category.contains(tokens[6]))
            return tokens[6].toLowerCase() as Category
        return new Taxon(tokens)
    }
}