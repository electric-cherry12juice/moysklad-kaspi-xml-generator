import requests
import base64
import xml.etree.ElementTree as ET
from datetime import datetime
from dotenv import load_dotenv
import os
from worker import app as celery_app


load_dotenv()


SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": "Basic " + base64.b64encode(os.getenv("MS_CREDENTIALS").encode()).decode(),
    "Accept-Encoding": "gzip"
})


def get_data(url='https://api.moysklad.ru/api/remap/1.2/entity/assortment', params={}):
    response = SESSION.get(url, params=params)
    data = response.json()
    return data


def get_assortment():
    data = get_data(params = {'filter': os.getenv("MS_FILTER")})
    products = []

    if data['rows']:
        for item in data['rows']: 

            product = {
                "article": None,
                "price": None,
                "stock": None
            }

            product.update({"article": str(item['code'])})
            product.update({"price" : str(int(item['salePrices'][0]['value'] // 100)) })

            if item['meta']['type'] == 'bundle':
                components_data = get_data(url=item['components']['meta']['href'])

                stock = 0
                for i in range(len(components_data['rows'])):
                    components_product_data = get_data(url=components_data['rows'][i]['assortment']['meta']['href'])
                    product_data = get_data(params = {'filter': f'code={components_product_data["code"]}'})
                    for inner_item in product_data['rows']:
                        stock += inner_item['stock']
                product.update({"stock" : str(int(stock))})

            else:
                product.update({"stock" : str(int(item['stock']))})

            if int(product["stock"]) > 0:
                products.append(product)

    return products


def generate_kaspi_xml(
    company: str,
    merchant_id: str,
    products: list[dict],
    store_id: str = "PP1",
    brand: str = os.getenv("MS_BRAND"),
    output_file: str = "static/kaspi_catalog.xml"
    ):

    root = ET.Element("kaspi_catalog", attrib={
        "xmlns": "kaspiShopping",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xsi:schemaLocation": "http://kaspi.kz/kaspishopping.xsd"
    })

    ET.SubElement(root, "company").text = company
    ET.SubElement(root, "merchantid").text = merchant_id

    offers_el = ET.SubElement(root, "offers")

    for item in products:
        stock = int(item["stock"])
        available = "yes" if stock > 0 else "no"
        offer = ET.SubElement(offers_el, "offer", attrib={"sku": item["article"]})
        ET.SubElement(offer, "model").text = item["article"]
        ET.SubElement(offer, "brand").text = brand
        availabilities = ET.SubElement(offer, "availabilities")
        ET.SubElement(availabilities, "availability", attrib={
            "available": available,
            "storeId": store_id,
            "stockCount": str(stock)
        })
        ET.SubElement(offer, "price").text = item["price"]

    ET.indent(root)

    tree = ET.ElementTree(root)

    tree.write(output_file, encoding="utf-8", xml_declaration=True)

    print(f"Сохранено: {output_file} ({len(products)} товаров)")


@celery_app.task(bind=True, name="tasks.update_kaspi_catalog")
def update_kaspi_catalog(self):
    self.update_state(state='PROGRESS', meta={'status': 'Получение данных из МойСклад...'})

    products = get_assortment()

    self.update_state(state='PROGRESS', meta={'status': f'Генерация XML для {len(products)} товаров...'})

    output_path = "static/kaspi_catalog.xml"

    generate_kaspi_xml(
        company=os.getenv("MS_COMPANY"), 
        merchant_id=os.getenv("MS_MERCHANT_ID"), 
        products=products, 
        store_id=os.getenv("MS_STORE_ID"), 
        brand=os.getenv("MS_BRAND"),
        output_file='static/kaspi_catalog.xml'
    )
    
    return {"status": "Complete", "file": "/static/kaspi_catalog.xml"}