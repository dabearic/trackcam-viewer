

export enum Category {
    ANIMAL = 'animal',
    HUMAN = 'human',
    VEHICLE =  'vehicle',
    UNKNOWN = 'unknown',
    BLANK = 'blank',
}
export namespace Category {
    export function contains(value: string){
        return Object.values(Category).includes(value.toLowerCase() as Category)
    }
}

export enum Source {
    INFERENCE = 'inference',
    DETECTOR = 'detector',
}

export class FloatRegion {
    minX: number
    minY: number
    maxX: number
    maxY: number
    width: number
    height: number
    constructor(minX: number, minY: number, width: number, height: number) {
        this.minX = minX
        this.minY = minY
        this.width = width
        this.height = height
        this.maxX = minX + width
        this.maxY = minY + height
    }

    public areaPercent(): number{
        return this.width * this.height * 100.0
    }
}

export class Taxon {
    id: string
    class?: string
    order?: string
    family?: string
    genus?: string
    species?: string
    common_name: string
    scientific: string
    raw: string
    custom: boolean

    public constructor(tokens: string[]) {
        if(tokens.length != 7){
            throw new RangeError('Expected exactly 7 tokens, got ' + tokens.length)
        } else {
            this.id = tokens[0]
            if(tokens[1]){
                this.class= tokens[1]
            }
            if(tokens[2]){
                this.order = tokens[2]
            }
            if(tokens[3]){
                this.family = tokens[3]
            }
            if(tokens[4]){
                this.genus = tokens[4]
            }
            if(tokens[5]){
                this.species = tokens[5]
            }
            this.common_name = tokens[6]
            if(this.genus && this.species)
                this.scientific = this.genus + " " + this.species
            this.raw = tokens.join(';')
            this.custom = false
        }
    }
    public contains(other: Taxon): boolean{
        if(other.id == this.id){
            return true
        } else {
          if(this.order != null && this.order != other.order){
                return false
            } else if(this.genus != null && this.genus != other.genus){
                return false
            }else if(this.species != null && this.species != other.species){
                return false
            } else {
                return true
            }
        }
    }
    public isSpecies(): boolean {
        return this.genus != null && this.species != null;
    }
}
export type Kind = Category | Taxon
export namespace Kind {
    export function label(value: Kind): string {
        if(value instanceof Taxon)
            return value.common_name
        else
            return value
    }
    export function getCategory(item: Kind): Category {
        if(item instanceof Taxon){
            let t = (item as Taxon)
            if(t.common_name.toLowerCase() == 'human')
                return Category.HUMAN
            else
                return Category.ANIMAL
        } else {
            return item
        }
    }

    export function getSpecies(item: Kind): Taxon | undefined {
        if(item instanceof Taxon)
            return item
        else
            return undefined
    }


}
export class Detection {
    bbox: FloatRegion
    category: Category
    classification ?: Taxon
    confidence: number
    cropPath: string
    parent: ImageInfo
    manual: boolean
    id: `${string}-${string}-${string}-${string}-${string}` = crypto.randomUUID()
    public label(): string{
        if (this.classification){
            return this.classification.common_name
        } else {
            return this.category as string
        }
    }
}
export class Prediction {
    classification: Kind
    category: Category
    score: number
    source: Source
    top5: Map<Kind, number>
    model_version: string
    country: string

    public label(): string {
        if(this.classification instanceof Taxon){
            return this.classification.common_name
        } else {
            return this.classification as string
        }
    }

    public top5Array(): Array<Taxon|Category> {
        return Array.from(this.top5.keys())
    }

    public isSpecies(): boolean {
        return this.classification instanceof Taxon
    }

    public species(): Taxon | undefined{
        return Kind.getSpecies(this.classification)
    }


}
export class ImageInfo {
    filepath: string
    filename: string
    prediction ?: Prediction
    detections: Detection[]
    cameraPosition: CameraPosition
    timestamp: Date
    taken_at ?: Date
    uploaded: Date
    failures: string[] = []

    isBlank(): boolean{
        if(this.prediction == null){
            return this.detections.length == 0
        } else {
            return this.prediction.classification == Category.BLANK;
        }
    }
    public isHuman(): boolean {
        if(this.isBlank())
            return false;
        if(this.prediction !== null){
            return this.prediction.classification == Category.HUMAN
        } else if(this.detections.length > 0){
            return this.detections.find(
                (value, index, obj)=>
                    value.category == Category.HUMAN) !== null
        } else {
            return false;
        }
    }

    public badges(): Map<string, number> {
        let counts = new Map<string, number>
        for(let det of this.detections){
            if (counts.has(det.label())){
                counts[det.label()]++
            } else {
                counts[det.label()] = 1
            }
        }
        if (!counts.has(this.prediction.label()))
            counts[this.prediction.label()] = 1;
        return
    }
}

export class Area {
    name: string
    code: string
    country?: string
    positions: Map<String, CameraPosition>
}

export class CameraPosition {
    name: string
    country: string
    state ?: string
    latitude?: number
    longitude?: number
    area: Area
    public label(): string {
        return this.area.code + "-" + this.name
    }
}

export class Job {
    status: string
    message: string
    log: Array<string>
    progress: Map<string, number>
    summary ?: Summary
    total: number


}

export class Summary {
    by_category?: []
    by_species?: []
    images: Array<ImageInfo>
    total: number
}