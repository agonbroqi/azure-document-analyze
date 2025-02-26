from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential
import base64
from collections import OrderedDict
from dotenv import load_dotenv
import os
from typing import List
import re
import tempfile
from azure.ai.documentintelligence import DocumentIntelligenceClient


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
       
        cleaned = re.sub(r'(\d+,\d+)\n\1', r'\1', str(value))
        return cleaned.strip()

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
                ("work_price", self.clean_value("work price", raw_data.get("work price total", ""))),
                ("material_price", self.clean_value("material price", raw_data.get("material price total", ""))),
                ("tax_basis", self.clean_value("tax basis", raw_data.get("tax basis", ""))),
                ("vat_percentage", raw_data.get("VAT percentage", "")),
                ("vat_total", self.clean_value("vat total", raw_data.get("VAT total", ""))),
                ("total_amount", self.clean_value("total amount", raw_data.get("total amount", "")))
            ])
        }

    async def analyze_document(self, file_content: bytes):
        try:
            base64_content = base64.b64encode(file_content).decode()
            
            poller = self.client.begin_analyze_document(
                model_id="final",
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
            print(f"Error in analyze_document: {str(e)}") 
            print(f"Endpoint: {self.endpoint}")  
            print(f"Model ID: final")  
            raise HTTPException(status_code=500, detail=str(e))

    def are_same_document(self, doc1: dict, doc2: dict) -> bool:
        
        identifiers = [
            
            (doc1["analysis"]["invoice_information"]["costumer_number"], 
             doc2["analysis"]["invoice_information"]["costumer_number"]),
            (doc1["analysis"]["invoice_information"]["order_number"], 
             doc2["analysis"]["invoice_information"]["order_number"]),
            (doc1["analysis"]["invoice_information"]["date_of_delivery"], 
             doc2["analysis"]["invoice_information"]["date_of_delivery"]),
            
            
            (doc1["analysis"]["vehicle_information"]["operating_number"], 
             doc2["analysis"]["vehicle_information"]["operating_number"]),
            (doc1["analysis"]["vehicle_information"]["first_registration"], 
             doc2["analysis"]["vehicle_information"]["first_registration"]),
            (doc1["analysis"]["vehicle_information"]["service_consultant"], 
             doc2["analysis"]["vehicle_information"]["service_consultant"]),
            (doc1["analysis"]["vehicle_information"]["km_status"], 
             doc2["analysis"]["vehicle_information"]["km_status"])
        ]
        
        
        matches = sum(1 for id1, id2 in identifiers if id1 and id2 and id1 == id2)
        
        
        print(f"Number of matches: {matches} out of {len(identifiers)}")
        print("Non-matching fields:")
        for i, (id1, id2) in enumerate(identifiers):
            if id1 != id2:
                print(f"Field {i}: '{id1}' vs '{id2}'")
        
        
        return matches >= 3

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
                model_id="license",  
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
        
        
        matches = 0
        if v1.get("fin") and v2.get("fin") and v1["fin"] == v2["fin"]:
            matches += 1
        if v1.get("model") and v2.get("model") and v1["model"] == v2["model"]:
            matches += 1
        if v1.get("marke") and v2.get("marke") and v1["marke"] == v2["marke"]:
            matches += 1
        
        
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

        
        for result in results:
            for field in combined["vehicle_information"]:
                if not combined["vehicle_information"][field] and result["analysis"]["vehicle_information"][field]:
                    combined["vehicle_information"][field] = result["analysis"]["vehicle_information"][field]

        return combined

@app.post("/analyze/")
async def analyze_files(files: List[UploadFile] = File(...)):
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        # If only one file, process it normally
        if len(files) == 1:
            return await process_single_file(files[0])
        
        # For multiple files, we need to validate they're the same document
        # and combine their information
        all_analyses = []
        filenames = []
        
        # Process each file individually
        for file in files:
            analysis = await process_single_file(file, return_raw=True)
            all_analyses.append(analysis)
            filenames.append(file.filename)
        
        # Validation fields to check if documents are the same
        validation_fields = [
            ("invoice_information", "invoice number"),
            ("invoice_information", "costumer number"),
            ("invoice_information", "order number"),
            ("vehicle_information", "operating number"),
            ("invoice_information", "unit/chassis number")
        ]
        
        # Check if all documents have the same key identifiers
        document_identifiers = {}
        
        # Extract identifiers from each document
        for i, analysis in enumerate(all_analyses):
            doc_id = {}
            for category, field in validation_fields:
                if category in analysis["analysis"] and field in analysis["analysis"][category]:
                    value = analysis["analysis"][category][field]
                    doc_id[f"{category}.{field}"] = value
            
            document_identifiers[i] = doc_id
        
        # Compare identifiers across documents
        mismatch_fields = []
        for field_key in set().union(*[set(doc.keys()) for doc in document_identifiers.values()]):
            values = set()
            for doc_id in document_identifiers.values():
                if field_key in doc_id:
                    values.add(doc_id[field_key])
            
            if len(values) > 1:
                mismatch_fields.append((field_key, values))
        
        # If we found mismatches, return an error
        if mismatch_fields:
            return {
                "status": "error",
                "message": "The uploaded files appear to be from different invoices",
                "mismatches": [
                    {
                        "field": field,
                        "values": list(values)
                    } for field, values in mismatch_fields
                ],
                "filenames": filenames
            }
        
        # If we get here, the documents are the same - combine their information
        combined_analysis = {
            "invoice_information": {},
            "vehicle_information": {},
            "financial_information": {}
        }
        
        # Combine all fields from all documents
        for analysis in all_analyses:
            for category in combined_analysis.keys():
                if category in analysis["analysis"]:
                    for field, value in analysis["analysis"][category].items():
                        # Only add if not already present or if the new value has more information
                        if field not in combined_analysis[category] or len(str(value)) > len(str(combined_analysis[category][field])):
                            combined_analysis[category][field] = value
        
        return {
            "status": "success",
            "analysis": combined_analysis,
            "filenames": filenames
        }
    
    except Exception as e:
        # Print detailed error for debugging
        import traceback
        print(f"Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")

# Helper function to process a single file
async def process_single_file(file, return_raw=False):
    file_content = await file.read()
    
    # Create the Document Intelligence client
    document_intelligence_client = DocumentIntelligenceClient(
        endpoint=os.environ["AZURE_ENDPOINT"],
        credential=AzureKeyCredential(os.environ["AZURE_KEY"])
    )
    
    # Analyze the document using your custom model "final"
    poller = document_intelligence_client.begin_analyze_document(
        "final",        # Your custom model name
        file_content    # document content as bytes
    )
    result = poller.result()
    
    # Extract fields from the document
    fields = result.documents[0].fields if result.documents else {}
    
    # Initialize our data structures
    invoice_information = {}
    vehicle_information = {}
    financial_information = {}
    
    # Clean financial values function
    def clean_financial_value(value):
        if not value:
            return value
            
        # Convert to string if it's not already
        value_str = str(value).strip()
        
        # If there are newlines, take only the first value
        if '\n' in value_str:
            return value_str.split('\n')[0].strip()
            
        return value_str
    
    # Process each field from the custom model
    for field_name, field_content in fields.items():
        field_value = ""
        if hasattr(field_content, 'content') and field_content.content:
            field_value = field_content.content
        elif hasattr(field_content, 'value') and field_content.value:
            field_value = field_content.value
        
        # Skip empty fields
        if not field_value:
            continue
            
        # Clean financial values
        if any(financial_term in field_name.lower() for financial_term in 
              ["price", "amount", "total", "vat", "tax", "sum"]):
            field_value = clean_financial_value(field_value)
        
        # Assign to the appropriate category
        if any(invoice_term in field_name.lower() for invoice_term in 
              ["invoice", "costumer", "order", "date", "registration", "chassis", "recording", "delivery"]):
            invoice_information[field_name] = field_value
        elif any(vehicle_term in field_name.lower() for vehicle_term in 
                ["km", "status", "vehicle", "car", "operating"]):
            vehicle_information[field_name] = field_value
        elif any(financial_term in field_name.lower() for financial_term in 
                ["price", "amount", "total", "vat", "tax", "sum"]):
            financial_information[field_name] = field_value
    
    # Move operating number to vehicle information if it's in invoice information
    if "operating number" in invoice_information:
        vehicle_information["operating number"] = invoice_information.pop("operating number")
    
    analysis_result = {
        "status": "success",
        "analysis": {
            "invoice_information": invoice_information,
            "vehicle_information": vehicle_information,
            "financial_information": financial_information
        },
        "filename": file.filename
    }
    
    if return_raw:
        return analysis_result
    else:
        return analysis_result

@app.post("/analyze-license/")
async def analyze_license(files: List[UploadFile] = File(...)):
    try:
        if not files:
            raise HTTPException(status_code=400, detail="No files provided")
        
        # Process all files
        combined_license_data = {}
        document_identifiers = set()
        license_plates = set()
        fin_numbers = set()
        
        for file_index, file in enumerate(files):
            # Read file content
            file_content = await file.read()
            
            # Create the Document Intelligence client
            document_intelligence_client = DocumentIntelligenceClient(
                endpoint=os.environ["AZURE_ENDPOINT"],
                credential=AzureKeyCredential(os.environ["AZURE_KEY"])
            )
            
            # Analyze the document using your custom model "full-license"
            poller = document_intelligence_client.begin_analyze_document(
                "full-license",  # model ID
                file_content,    # document content as bytes
            )
            result = poller.result()
            
            # Check if we have documents in the result
            if not result.documents:
                raise HTTPException(
                    status_code=400, 
                    detail=f"File {file_index + 1} ({file.filename}) could not be analyzed as a license document"
                )
            
            # Extract document identifiers
            fields = result.documents[0].fields
            
            # Check license plate
            license_plate = None
            if "A: Licence plate" in fields:
                field = fields["A: Licence plate"]
                if hasattr(field, 'content') and field.content:
                    license_plate = field.content
                    license_plates.add(license_plate)
            
            # Check FIN/VIN
            fin = None
            if "E: FIN" in fields:
                field = fields["E: FIN"]
                if hasattr(field, 'content') and field.content:
                    fin = field.content
                    fin_numbers.add(fin)
            
            # Create a document identifier
            doc_identifier = f"Doc-{file_index}"
            if license_plate:
                doc_identifier = f"License:{license_plate}"
            elif fin:
                doc_identifier = f"FIN:{fin}"
            
            document_identifiers.add(doc_identifier)
            
            # Process each field
            for field_name, field_content in fields.items():
                # Check if the field has content
                if hasattr(field_content, 'content') and field_content.content:
                    # Only add if not already present or if the new value has more information
                    if field_name not in combined_license_data or len(field_content.content) > len(combined_license_data[field_name]):
                        combined_license_data[field_name] = field_content.content
                # Check if the field has a value property
                elif hasattr(field_content, 'value') and field_content.value:
                    if field_name not in combined_license_data or len(str(field_content.value)) > len(str(combined_license_data[field_name])):
                        combined_license_data[field_name] = field_content.value
        
        # Validate that all documents are the same
        if len(license_plates) > 1 or len(fin_numbers) > 1:
            return {
                "error": "The uploaded files appear to be from different vehicles.",
                "license_plates": list(license_plates),
                "fin_numbers": list(fin_numbers)
            }
        
        # Return the combined results
        return {"license_data": combined_license_data}
    
    except Exception as e:
        # Print detailed error for debugging
        import traceback
        print(f"Error: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(e)}")