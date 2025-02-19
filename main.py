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
        """Clean and format field values."""
        if not value:
            return ""
        return str(value).strip()

    def organize_data(self, raw_data: dict) -> dict:
        """Organize raw data into structured format."""
        return {
            "invoice_information": {
                "invoice_number": raw_data.get("invoice number", ""),
                "costumer_number": raw_data.get("costumer number", ""),
                "order_number": raw_data.get("order number", ""),
                "date_of_delivery": raw_data.get("date/day of delivery", "")
            },
            "vehicle_information": {
                "operating_number": raw_data.get("operating number", ""),
                "first_registration": raw_data.get("date of first registration", ""),
                "service_consultant": raw_data.get("service consultant", ""),
                "km_status": raw_data.get("km-status", "")
            },
            "financial_information": OrderedDict([
                ("work_price", raw_data.get("work price total", "")),
                ("material_price", raw_data.get("material price total", "")),
                ("tax_basis", raw_data.get("tax basis", "")),
                ("vat_percentage", raw_data.get("VAT percentage", "")),
                ("vat_total", raw_data.get("VAT total", "")),
                ("total_amount", raw_data.get("total amount", ""))
            ])
        }

    async def analyze_document(self, file_content: bytes):
        try:
            base64_content = base64.b64encode(file_content).decode()
            
            poller = self.client.begin_analyze_document(
                model_id="final",  # Just the model name
                body={"base64Source": base64_content}
            )
            
            result = poller.result()
            
            if hasattr(result, 'documents') and result.documents:
                for document in result.documents:
                    fields = document.fields
                    raw_data = {}
                    for name, field in fields.items():
                        if field is not None:
                            raw_data[name] = self.clean_value(name, field.content or "")
                    return self.organize_data(raw_data)
            
            raise ValueError("No document information found")
            
        except Exception as e:
            print(f"Error in analyze_document: {str(e)}")  # More detailed error logging
            print(f"Endpoint: {self.endpoint}")  # Log endpoint
            print(f"Model ID: final")  # Log model ID
            raise HTTPException(status_code=500, detail=str(e))

    def are_same_document(self, doc1: dict, doc2: dict) -> bool:
        # Check all fields that should match
        identifiers = [
            # Invoice Information
            (doc1["analysis"]["invoice_information"]["costumer_number"], 
             doc2["analysis"]["invoice_information"]["costumer_number"]),
            (doc1["analysis"]["invoice_information"]["order_number"], 
             doc2["analysis"]["invoice_information"]["order_number"]),
            (doc1["analysis"]["invoice_information"]["date_of_delivery"], 
             doc2["analysis"]["invoice_information"]["date_of_delivery"]),
            
            # Vehicle Information
            (doc1["analysis"]["vehicle_information"]["operating_number"], 
             doc2["analysis"]["vehicle_information"]["operating_number"]),
            (doc1["analysis"]["vehicle_information"]["first_registration"], 
             doc2["analysis"]["vehicle_information"]["first_registration"]),
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
        
        # Return True if at least 3 identifiers match
        return matches >= 3

    def combine_results(self, results: List[dict]) -> dict:
        # Verify all documents are from the same source
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

        # Initialize combined result with empty values
        combined = {
            "invoice_information": {
                "invoice_number": "",
                "costumer_number": "",
                "order_number": "",
                "date_of_delivery": ""
            },
            "vehicle_information": {
                "operating_number": "",
                "first_registration": "",
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

        # Update with non-empty values from all results
        for result in results:
            for section in combined:
                for field in combined[section]:
                    if not combined[section][field] and result["analysis"][section][field]:
                        combined[section][field] = result["analysis"][section][field]

        return combined

    async def analyze_license_document(self, file_content: bytes):
        try:
            base64_content = base64.b64encode(file_content).decode()
            
            poller = self.client.begin_analyze_document(
                model_id="license",  # Use license model
                body={"base64Source": base64_content}
            )
            
            result = poller.result()
            
            if hasattr(result, 'documents') and result.documents:
                for document in result.documents:
                    fields = document.fields
                    raw_data = {}
                    for name, field in fields.items():
                        if field is not None:
                            raw_data[name] = self.clean_value(name, field.content or "")
                    return self.organize_license_data(raw_data)
            
            raise ValueError("No document information found")
            
        except Exception as e:
            print(f"Error during analysis: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def organize_license_data(self, raw_data: dict) -> dict:
        return {
            "vehicle_information": {
                "model": raw_data.get("model", ""),
                "marke": raw_data.get("marke", ""),
                "fin": raw_data.get("fin", ""),
                "erstzulassung": raw_data.get("erstzulassung", ""),
                "letze_wartung": raw_data.get("letze wartung", ""),
                "type_variant_version": raw_data.get("type/variant/version", "")
            }
        }

    def are_same_vehicle(self, doc1: dict, doc2: dict) -> bool:
        # Check vehicle-specific fields
        v1 = doc1["analysis"]["vehicle_information"]
        v2 = doc2["analysis"]["vehicle_information"]
        
        # Count matching fields
        matches = 0
        if v1.get("fin") and v2.get("fin") and v1["fin"] == v2["fin"]:
            matches += 1
        if v1.get("model") and v2.get("model") and v1["model"] == v2["model"]:
            matches += 1
        if v1.get("marke") and v2.get("marke") and v1["marke"] == v2["marke"]:
            matches += 1
        
        # Return True if at least 2 identifiers match
        return matches >= 2

    def combine_license_results(self, results: List[dict]) -> dict:
        combined = {
            "vehicle_information": {
                "model": "",
                "marke": "",
                "fin": "",
                "erstzulassung": "",
                "letze_wartung": "",
                "type_variant_version": ""
            }
        }

        # Update with non-empty values from all results
        for result in results:
            for field in combined["vehicle_information"]:
                if not combined["vehicle_information"][field] and result["analysis"]["vehicle_information"][field]:
                    combined["vehicle_information"][field] = result["analysis"]["vehicle_information"][field]

        return combined

@app.post("/analyze/")
async def analyze_files(
    files: List[UploadFile] = File(...)
):
    try:
        processor = DocumentProcessor()
        results = []
        
        # Validate file types
        for f in files:
            if not f.filename.lower().endswith(('.pdf', '.jpg', '.jpeg')):
                raise HTTPException(
                    status_code=400,
                    detail=f"File {f.filename} is not a PDF or JPG/JPEG file"
                )
        
        # Process all files
        for f in files:
            content = await f.read()
            result = await processor.analyze_document(content)
            results.append({
                "filename": f.filename,
                "analysis": result
            })
            
        # If we have multiple files, verify they're from the same document
        if len(results) > 1:
            # Compare each file with the next one
            for i in range(len(results)-1):
                if not processor.are_same_document(results[i], results[i+1]):
                    return {
                        "error": "Different documents detected",
                        "message": "The uploaded files appear to be from different documents.",
                        "details": {
                            "files": [r["filename"] for r in results],
                            "mismatched_files": [
                                results[i]["filename"],
                                results[i+1]["filename"]
                            ]
                        }
                    }
            
            # If all files match, combine their results
            combined_result = processor.combine_results(results)
            return {
                "status": "success",
                "message": "Combined documents",
                "combined_analysis": combined_result,
                "original_files": [r["filename"] for r in results]
            }
        else:
            # Single file case
            return {
                "status": "success",
                "message": "Single file processed",
                "analysis": results[0]["analysis"],
                "filename": results[0]["filename"]
            }
            
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error processing files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-license/")
async def analyze_license(
    files: List[UploadFile] = File(default=[])
):
    try:
        processor = DocumentProcessor()
        results = []
        
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
            
        # Process all files with license model
        for f in files:
            content = await f.read()
            # Use license model instead of final
            result = await processor.analyze_license_document(content)
            results.append({
                "filename": f.filename,
                "analysis": result
            })
            
        # If we have multiple files, verify they're from the same vehicle
        if len(results) > 1:
            # Compare each file with the next one
            for i in range(len(results)-1):
                if not processor.are_same_vehicle(results[i], results[i+1]):
                    return {
                        "error": "Different vehicles detected",
                        "message": "The uploaded files appear to be from different vehicles.",
                        "details": {
                            "files": [r["filename"] for r in results],
                            "mismatched_files": [
                                results[i]["filename"],
                                results[i+1]["filename"]
                            ]
                        }
                    }
            
            # If all files match, combine their results
            combined_result = processor.combine_license_results(results)
            return {
                "status": "success",
                "message": "Combined documents",
                "combined_analysis": combined_result,
                "original_files": [r["filename"] for r in results]
            }
        else:
            # Single file case
            return {
                "status": "success",
                "message": "Single file processed",
                "analysis": results[0]["analysis"],
                "filename": results[0]["filename"]
            }
            
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error processing files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))