from fastapi import FastAPI, File, UploadFile, HTTPException
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
import base64
from collections import OrderedDict
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

class DocumentProcessor:
    def __init__(self):
        # Get credentials from .env file
        self.endpoint = os.getenv("AZURE_ENDPOINT")
        self.key = os.getenv("AZURE_KEY")
        
        if not self.endpoint or not self.key:
            raise ValueError("Azure credentials not found in .env file")
        
        self.client = DocumentIntelligenceClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.key)
        )

    def clean_value(self, field_name: str, value: str) -> str:
        if not value:
            return ""
            
        
        if field_name == "company name":
            print(f"Raw company name value: '{value}'")
            
        
        if "\n" in value:
            value = value.split("\n")[0]
            
        
        if value.startswith("UID:"):
            value = value.replace("UID:", "")
            
        #
        if field_name == "company name":
            return value
            
        
        if value == "Summe":
            value = ""
            
        return value.strip()

    def organize_data(self, extracted_data: dict) -> dict:
        
        financial_info = OrderedDict([
            ("work_price", extracted_data.get("work price total", "")),
            ("material_price", extracted_data.get("material price total", "")),
            ("tax_basis", extracted_data.get("tax basis", "")),
            ("vat_percentage", extracted_data.get("VAT percentage", "")),
            ("vat_total", extracted_data.get("VAT total", "")),
            ("total_amount", extracted_data.get("total amount", ""))
        ])

        return {
            "company_information": {
                "company_name": extracted_data.get("company name", ""),
                "company_address": extracted_data.get("company address", "")
            },
            "invoice_information": {
                "invoice_number": extracted_data.get("invoice number", ""),
                "customer_number": extracted_data.get("costumer number", ""),
                "order_number": extracted_data.get("order number", ""),
                "date_of_delivery": extracted_data.get("date/day of delivery", "")
            },
            "vehicle_information": {
                "uid": extracted_data.get("UID", ""),
                "operating_number": extracted_data.get("operating number", ""),
                "official_label": extracted_data.get("official label", ""),
                "type_model": extracted_data.get("type/model", ""),
                "first_registration": extracted_data.get("date of first registration", ""),
                "chassis_number": extracted_data.get("unit/chassis number", ""),
                "installation_date": extracted_data.get("installation/recording date", ""),
                "service_consultant": extracted_data.get("service consultant", ""),
                "km_status": extracted_data.get("km-status", "")
            },
            "financial_information": financial_info
        }

    async def analyze_document(self, file_content: bytes):
        try:
            
            base64_content = base64.b64encode(file_content).decode()
            
            
            body = {
                "base64Source": base64_content
            }
            
            # Send request with body
            poller = self.client.begin_analyze_document(
                model_id="final",
                body=body
            )
            
            result = poller.result()

            raw_data = {}
            
            if hasattr(result, 'documents') and result.documents:
                for document in result.documents:
                    for name, field in document.fields.items():
                        if field is not None:
                            raw_data[name] = self.clean_value(name, field.content or "")

            
            return self.organize_data(raw_data)

        except Exception as e:
            print(f"Error during analysis: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze/")
async def analyze_file(file: UploadFile = File(...)):
    processor = DocumentProcessor()
    content = await file.read()
    return await processor.analyze_document(content)