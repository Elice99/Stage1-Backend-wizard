from fastapi import FastAPI, HTTPException, Query 
from pydantic import BaseModel
from typing import Optional, List, Dict
from hashlib import sha256
from datetime import datetime

app = FastAPI()

#A dict to act as our in memory database; keys are sha256 hash of str, values are analysis result
db = {}

#Define pydantic model to validate incoming JSON request body for POST/str endpoint
class StringInput(BaseModel):
    value: str   # expect a field called 'value' of type str in the input JSON
    
# A helper function that computes all the requested str properties
def analyze_string(s: str) -> Dict:
    lower = s.lower() 
    length = len(s)
    is_palindrome = lower == lower[::-1] # check if str reads same foward and backwards
    unique_characters = len(set(s))  # count distinct characters using set
    words_count = len(s.splits()) # count words seperated by whitespace
    hash_value = sha256(s.encode()).hexdigest() # SHA256 hash for unique ID (encode str as bytes)
    char_freq = {}  # Dict to count frequency of each character
    for char in s: # loop tru every character
        char_freq[char] = char_freq.get(char, 0) + 1 # increment count for this charater
        
        #return all computed properties as a dict
        return{
            'length': length,
            'is_palindrome': is_palindrome,
            'unique_character':unique_characters,
            'word_count': words_count,
            'sha256_hash': hash_value,
            'character_frequency_map':char_freq 
        }
        
# Endpoint 1: Create/Analyse str (HTTP POST)
@app.post("/strings", status_code=201)  # declare route and response code(201 = created)
def create_string(inpute: StringInput):   #Accept validate StringInput model
    
    # validate input type - although pydantic ensures this usually
    if not isinstance(input.value, str):
        raise HTTPException(status_code=422, detail = "Invalid date type 'value'(must be str) " )
    
    #check for empty str input
    if input.value == "":
        raise HTTPException(status_code=400, detail = "Missing 'value' field")
    #compute string properties
    props = analyze_string(input.value)
    
    #check if str already analyzed based on hash256 key
    if props["sha256_hash"] in db:
        raise HTTPException(status_code=409, detail= 'String already exists in the system')
    
    # get current time in UTC ISO format with a Z to mark UTC
    now_iso = datetime.utcnow().isoformat() + 'Z'
    
    #create records obj with al the info inclusive of computed properties and timestamps
    record = {
        'id': props['sha256_hash'],
        'value': input.value,
        'properties': props,
        'created_at': now_iso
    }
    
    #store the record in our in memory database keyed by hash
    db[props['sha256_hash']] = record
    
    #return the record to the client
    return record

# helper function to find stored str recored by its raw str value
def find_strings_record(s: str):
    hash_value = sha256(s.encode()).hexdigest() # compute hash of str to use as key
    return db.get(hash_value) # return records from db or None if not found

#Endpoin 2: get specific str (HTTP GET)
@app.get("/strings/{string_value}")
def get_string(string_value: str):  # Accept str value from url
    record = find_strings_record(string_value)   # find stored record by hashed str
    if not record:  # if not found throw 404 error
        raise HTTPException(status_code=404, detail= "String does not exist in the system")
    return record  #return found record

#Endpoint 3: get all str with filtering (HTTP GET with query parameters)
@app.get("/strings")
def get_all_strings(
    is_palindrome: Optional[bool] = Query(None), # Filters: optional boolean query para
    min_length: Optional[int] = Query(None), # Minimum length filter
    max_length: Optional[int] = Query(None), # Maximum length filter
    word_count: Optional[int] = Query(None), # Exact word count filter
    contains_character: Optional[str] = Query(None, min_length= 1, max_length= 1)  # contains character filter (one char only)
        ):
    results = []
    for record in db.values():  #Iterate all stored str record
        props = record['properties']
        
        # apply filters one by one skip records that dont mark
        if is_palindrome is not None and props['is_palindrome'] != is_palindrome:
            continue
        if min_length is not None and props['length'] < min_length:
            continue
        if max_length is not None and props['length'] > max_length:
            continue
        if word_count is not None and props['word_count'] != word_count:
            continue
        if contains_character is not None and contains_character not in record['value']:
            continue
        
        results.append(record) #add matching record to result list
        
        #build summary of filters applied to return in response
        filters_applied = {}
        if is_palindrome is not None:
            filters_applied['is_palindrome'] = is_palindrome
        if min_length is not None:
            filters_applied['min_length'] = min_length
        if max_length is not None:
            filters_applied['max_length'] = max_length
        if word_count is not None:
            filters_applied['word_count'] = word_count
        if contains_character is not None:
            filters_applied['contains_character'] = contains_character 
            
        # return results along with count and applied filters
        return{
            'data': results,
            'count': len(results),
            'filter_applied': filters_applied
        }
        
# A simple natural language query parser that maps example phrases to filters
def parse_natural_language(query: str) -> Dict:
    lower = query.lower()
    filters = {}
    
    #Map single word or one word phrases to word_count = 1
    if 'single word' in lower or 'one word' in lower:
        filters['word_count'] = 1
    
    # map palindromic or palindrome to is_palidrome=True
    if 'palindromic' in lower or 'palindrome' in lower:
        filters['is_palindrome'] = True
        
    # map str longer than x to min_length = x+1 using regex
    if 'strings longer than' in lower:
        import re
        m = re.search(r'strings longer than (d+)', lower)
        if m:
            filters['min_length'] = int (m.group(1))+1
            
    #map containing the letter x to contain_character=x using regex
    if 'containing the letter' in lower:
        import re
        m = re.search(r'containing the letter(w)', lower)
        if m:
            filters['contains_character'] = m.group(1)
    
    # Raise error if no known phrases found
    if not filters:
        raise HTTPException(status_code=400, detail="Unable to parse natural language query")# Check for conflicting filters (example check)
    
    if filters.get("min_length") is not None and filters.get("max_length") is not None:
        if filters["min_length"] > filters["max_length"]:
            raise HTTPException(status_code=422, detail="Query parsed but resulted in conflicting filters")

    return filters
    
# Endpoint 4: Natural Language Filtering (HTTP GET)
@app.get("/strings/filter-by-natural-language")
def filter_by_natural_language(query: str):
    filters = parse_natural_language(query)  # Parse natural language query into filters

    results = []
    for record in db.values():
        prop = record["properties"]
        # Apply parsed filter conditions same as before
        if "is_palindrome" in filters and prop["is_palindrome"] != filters["is_palindrome"]:
            continue
        if "min_length" in filters and prop["length"] < filters["min_length"]:
            continue
        if "max_length" in filters and prop["length"] > filters["max_length"]:
            continue
        if "word_count" in filters and prop["word_count"] != filters["word_count"]:
            continue
        if "contains_character" in filters and filters["contains_character"] not in record["value"]:
            continue
        results.append(record)
        
        # Return matched data plus interpreted query info
    return {
        "data": results,
        "count": len(results),
        "interpreted_query": {
            "original": query,
            "parsed_filters": filters
        }
    }
    
    # Endpoint 5: Delete String (HTTP DELETE)
@app.delete("/strings/{string_value}", status_code=204)
def delete_string(string_value: str):
    record = find_strings_record(string_value)  # Find record by string value
    if not record:  # If not found, raise 404 error
        raise HTTPException(status_code=404, detail="String does not exist in the system")
    del db[record["id"]]  # Delete record from storage by hash key
    return {}  # Return empty response with 204 status.
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
        
    
    
