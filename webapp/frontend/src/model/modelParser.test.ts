import {expect, expectTypeOf, test} from 'vitest'
import {parseJsonImage, parseKind} from './modelParser.ts'
import {Category, Kind, Taxon} from "./model.ts";

test('parses category kind', ()=>{
    expect(parseKind("human")).toEqual(Category.HUMAN)
    expect(parseKind("animal")).toEqual(Category.ANIMAL)
    expect(parseKind("vehicle")).toEqual(Category.VEHICLE)
    expect(parseKind("unknown")).toEqual(Category.UNKNOWN)
    expect(parseKind("blank")).toEqual(Category.BLANK)
    expect(parseKind("HUMAN"), "Human ignore caps").toEqual(Category.HUMAN)
    expect(parseKind("Human"), "Human ignore camel").toEqual(Category.HUMAN)

})

test('parses taxon kind', ()=>{
    let kind = parseKind("aaf3b049-36e6-46dd-9a07-8a580e9618b7;mammalia;carnivora;canidae;canis;latrans;coyote")
    expectTypeOf<Kind>(kind).exclude<Category>().toEqualTypeOf<Taxon>()
    let taxon = kind as Taxon
    expect(taxon.id, "ID").toEqual("aaf3b049-36e6-46dd-9a07-8a580e9618b7")
    expect(taxon.class, "class").toEqual('mammalia')
    expect(taxon.order, "order").toEqual('carnivora')
    expect(taxon.family, "family").toEqual('canidae')
    expect(taxon.genus, "genus").toEqual("canis")
    expect(taxon.species, "species").toEqual("latrans")
    expect(taxon.common_name, "Common Name").toEqual('coyote')
    expect(taxon.scientific).toEqual("canis latrans")

    let kind2 = parseKind("f2d233e3-80e3-433d-9687-e29ecc7a467a;mammalia;;;;;mammal")
    expectTypeOf<Kind>(kind).exclude<Category>().toEqualTypeOf<Taxon>()
    let taxon2 = kind2 as Taxon
    expect(taxon2.id).toEqual('f2d233e3-80e3-433d-9687-e29ecc7a467a')
    expect(taxon2.class).toEqual("mammalia")
    expect(taxon2.order).toBeUndefined()
    expect(taxon2.family).toBeUndefined()
    expect(taxon2.genus).toBeUndefined()
    expect(taxon2.species).toBeUndefined()
    expect(taxon2.scientific).toBeUndefined()

    expect(taxon2.contains(taxon)).toEqual(true)
    expect(taxon.contains(taxon2)).toEqual(false)
})

test("parses category in extended string", () =>{
    let val = parseKind("e2895ed5-780b-48f6-8a11-9e27cb594511;;;;;;vehicle")
    expect(val).toEqual(Category.VEHICLE)
})

test('fails to parse invalid strings', ()=>{
    try {
        parseKind("abcd")
    } catch (e) {
        expect(e instanceof RangeError, "random string").toEqual(true)
    }
    try {
        parseKind(";;;;;;;;")
    }
    catch (e) {
        expect(e instanceof RangeError, "empty semicolons").toEqual(true)
    }
})

test('parse full image', async ()=>{
    const fs = require('node:fs/promises')
    let jsonString = await fs.readFile('src/model/singleImage.json', 'utf8')
    let value = parseJsonImage(JSON.parse(jsonString))
    expect(value.prediction, "Has prediction").toBeDefined()
    expect(value.prediction.score).approximately(0.988,1e5, "Score value")
    expect(value.prediction.species()?.common_name).toEqual("coyote")
    expect(value.prediction.top5.size).toEqual(5)
    expect(value.prediction.top5.values()).toContain(0.988)
    expect(value.prediction.top5.values()).toContain(0.0014)
    expect(value.prediction.top5.values()).toContain(0.0012)
    expect(value.prediction.top5.values()).toContain(0.0011)
    expect(value.prediction.top5.values()).toContain(0.0006)
    expect(value.detections.length).toEqual(4)
    expect(value.detections.map((det)=>det.category)
        .every((c)=>c === Category.ANIMAL))
    expect(value.detections[0].confidence).toEqual(0.8762)
    expect(value.detections[1].bbox.areaPercent()).approximately(2.558, 1e5, "Area value")
})