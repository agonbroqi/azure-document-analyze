from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
import base64
from collections import OrderedDict
from dotenv import load_dotenv
import os
from typing import List


load_dotenv()

app = FastAPI()

class DocumentProcessor:
    def __init__(self):
       
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

            all_documents = []
            
            if hasattr(result, 'documents') and result.documents:
                for document in result.documents:
                    raw_data = {}
                    for name, field in document.fields.items():
                        if field is not None:
                            raw_data[name] = self.clean_value(name, field.content or "")
                    all_documents.append(self.organize_data(raw_data))

            # If only one document was processed, return it directly
            if len(all_documents) == 1:
                return all_documents[0]
            
          
            return {
                "documents": all_documents,
                "total_documents": len(all_documents)
            }

        except Exception as e:
            print(f"Error during analysis: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def are_same_document(self, doc1: dict, doc2: dict) -> bool:
        # Check all fields that should match
        identifiers = [
            # Invoice Information
            (doc1["analysis"]["invoice_information"]["customer_number"], 
             doc2["analysis"]["invoice_information"]["customer_number"]),
            (doc1["analysis"]["invoice_information"]["order_number"], 
             doc2["analysis"]["invoice_information"]["order_number"]),
            (doc1["analysis"]["invoice_information"]["date_of_delivery"], 
             doc2["analysis"]["invoice_information"]["date_of_delivery"]),
            
            # Vehicle Information
            (doc1["analysis"]["vehicle_information"]["uid"], 
             doc2["analysis"]["vehicle_information"]["uid"]),
            (doc1["analysis"]["vehicle_information"]["operating_number"], 
             doc2["analysis"]["vehicle_information"]["operating_number"]),
            (doc1["analysis"]["vehicle_information"]["official_label"], 
             doc2["analysis"]["vehicle_information"]["official_label"]),
            (doc1["analysis"]["vehicle_information"]["type_model"], 
             doc2["analysis"]["vehicle_information"]["type_model"]),
            (doc1["analysis"]["vehicle_information"]["first_registration"], 
             doc2["analysis"]["vehicle_information"]["first_registration"]),
            (doc1["analysis"]["vehicle_information"]["chassis_number"], 
             doc2["analysis"]["vehicle_information"]["chassis_number"]),
            (doc1["analysis"]["vehicle_information"]["installation_date"], 
             doc2["analysis"]["vehicle_information"]["installation_date"]),
            (doc1["analysis"]["vehicle_information"]["service_consultant"], 
             doc2["analysis"]["vehicle_information"]["service_consultant"]),
            (doc1["analysis"]["vehicle_information"]["km_status"], 
             doc2["analysis"]["vehicle_information"]["km_status"])
        ]
        
        # Count how many identifiers match
        matches = sum(1 for id1, id2 in identifiers if id1 and id2 and id1 == id2)
        
        # Log the number of matches for debugging
        print(f"Number of matches: {matches} out of {len(identifiers)}")
        print("Non-matching fields:")
        for i, (id1, id2) in enumerate(identifiers):
            if id1 != id2:
                print(f"Field {i}: '{id1}' vs '{id2}'")
        
        # Return True if at least 5 identifiers match
        return matches >= 5

    def combine_results(self, results: List[dict]) -> dict:
     
        for i in range(len(results)-1):
            if not self.are_same_document(results[i], results[i+1]):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Different documents detected",
                        "message": "The uploaded files appear to be from different documents. Please upload pages from the same document.",
                        "files": [r["filename"] for r in results]
                    }
                )

       
        combined = {
            "company_information": {
                "company_name": "",
                "company_address": ""
            },
            "invoice_information": {
                "invoice_number": "",
                "customer_number": "",
                "order_number": "",
                "date_of_delivery": ""
            },
            "vehicle_information": {
                "uid": "",
                "operating_number": "",
                "official_label": "",
                "type_model": "",
                "first_registration": "",
                "chassis_number": "",
                "installation_date": "",
                "service_consultant": "",
                "km_status": ""
            },
            "financial_information": OrderedDict([
                ("work_price", ""),
                ("material_price", ""),
                ("tax_basis", ""),
                ("vat_percentage", ""),
                ("vat_total", ""),
                ("total_amount", "")
            ])
        }

        for result in results:
            for section in combined:
                for field in combined[section]:
                    if not combined[section][field] and result["analysis"][section][field]:
                        combined[section][field] = result["analysis"][section][field]

        return combined

@app.post("/analyze/")
async def analyze_files(
    file: UploadFile = File(None),
    files: List[UploadFile] = File(None)
):
    try:
        processor = DocumentProcessor()
        results = []
        
      
        if file and not files:
            content = await file.read()
            result = await processor.analyze_document(content)
            results.append({
                "filename": file.filename,
                "analysis": result
            })
        
    
        elif files and not file:
            for f in files:
                content = await f.read()
                result = await processor.analyze_document(content)
                results.append({
                    "filename": f.filename,
                    "analysis": result
                })
        else:
            raise HTTPException(status_code=400, detail="Please provide either 'file' or 'files'")
        
       
        if len(results) > 1:
            combined_result = processor.combine_results(results)
            return {
                "combined_analysis": combined_result,
                "original_files": [r["filename"] for r in results]
            }
        else:
         
            return results[0]
            
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))