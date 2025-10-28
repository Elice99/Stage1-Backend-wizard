from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, validator
from typing import Optional, Dict, List
from hashlib import sha256
from datetime import datetime
import re
import uvicorn

# Initialize FastAPI application with a title
app = FastAPI(title="String Analyzer API") 

# In-memory store for strings keyed by sha256 hash
# This serves as the temporary database for the service.
db = {}

# Pydantic model for request body validation (POST /strings)
class StringInput(BaseModel):
    value: str

    # Custom validator to enforce non-empty string requirement
    @validator('value')
    def non_empty_string(cls, v):
        if not isinstance(v, str):
            # This case is usually handled by Pydantic, but explicit check adds safety
            raise ValueError("Must be a string")
        if v == "":
            # Ensures 422 Unprocessable Entity for empty strings
            raise ValueError("Value cannot be empty")
        return v

# Core function to compute all required string properties
def analyze_string(s: str) -> Dict:
    lower = s.lower()  # Used for case-insensitive palindrome check
    length = len(s)
    is_palindrome = lower == lower[::-1] # Checks if string reads the same forwards and backwards
    unique_characters = len(set(s))
    word_count = len(s.split()) # Splits by whitespace to count words
    hash_value = sha256(s.encode()).hexdigest() # SHA-256 for unique ID
    
    # Calculate character frequency map
    char_freq = {}
    for char in s:
        char_freq[char] = char_freq.get(char, 0) + 1
        
    return {
        "length": length,
        "is_palindrome": is_palindrome,
        "unique_characters": unique_characters,
        "word_count": word_count,
        "sha256_hash": hash_value,
        "character_frequency_map": char_freq
    }

# 1. Create/Analyze String (POST /strings)
@app.post("/strings", status_code=201)
def create_string(input: StringInput):
    props = analyze_string(input.value)
    hash_id = props["sha256_hash"]
    
    # 409 Conflict check: String already exists
    if hash_id in db:
        raise HTTPException(status_code=409, detail="String already exists")

    # Format timestamp strictly to required ISO 8601 format (e.g., 2025-08-27T10:00:00Z)
    now_iso = datetime.utcnow().isoformat(timespec='seconds') + "Z"
    
    # Prepare and store the full record
    record = {
        "id": hash_id,
        "value": input.value,
        "properties": props,
        "created_at": now_iso
    }

    db[hash_id] = record
    return record

# Helper function to find a string record by its value (by hashing it)
def find_string_record(s: str):
    hash_value = sha256(s.encode()).hexdigest()
    return db.get(hash_value)

# 2. Get Specific String (GET /strings/{string_value})
@app.get("/strings/{string_value}")
def get_string(string_value: str):
    record = find_string_record(string_value)
    
    # 404 Not Found check
    if not record:
        raise HTTPException(status_code=404, detail="String not found")
    return record

# 3. Get All Strings with Filtering (GET /strings)
@app.get("/strings")
def get_all_strings(
    is_palindrome: Optional[bool] = Query(None),
    min_length: Optional[int] = Query(None, ge=0),
    max_length: Optional[int] = Query(None, ge=0),
    word_count: Optional[int] = Query(None, ge=0),
    contains_character: Optional[str] = Query(None, min_length=1, max_length=1) # Enforces single character
):
    results = []
    
    for record in db.values():
        prop = record["properties"]
        
        # Apply filters sequentially, skipping record on mismatch
        if is_palindrome is not None and prop["is_palindrome"] != is_palindrome:
            continue
        if min_length is not None and prop["length"] < min_length:
            continue
        if max_length is not None and prop["length"] > max_length:
            continue
        if word_count is not None and prop["word_count"] != word_count:
            continue
        
        # Check if the character exists in the character frequency map keys
        if contains_character is not None:
            if contains_character not in prop["character_frequency_map"]:
                 continue

        results.append(record)
        
    # Build dictionary of applied filters for the response
    filters_applied = {}
    if is_palindrome is not None:
        filters_applied["is_palindrome"] = is_palindrome
    if min_length is not None:
        filters_applied["min_length"] = min_length
    if max_length is not None:
        filters_applied["max_length"] = max_length
    if word_count is not None:
        filters_applied["word_count"] = word_count
    if contains_character is not None:
        filters_applied["contains_character"] = contains_character
        
    # Return count and applied filters as required
    return {
        "data": results,
        "count": len(results),
        "filters_applied": filters_applied
    }

# Helper function for natural language query parsing
def parse_natural_language(query: str) -> Dict:
    lower = query.lower()
    filters = {}

    # Basic keyword parsing
    if "single word" in lower or "one word" in lower:
        filters["word_count"] = 1
    if "palindromic" in lower or "palindrome" in lower:
        filters["is_palindrome"] = True
    
    # Regex for "strings longer than N" -> min_length = N + 1
    if "strings longer than" in lower:
        m = re.search(r"strings longer than (\d+)", lower)
        if m:
            filters["min_length"] = int(m.group(1)) + 1
            
    # Regex for "containing the letter W"
    if "containing the letter" in lower:
        m = re.search(r"containing the letter (\w)", lower)
        if m:
            filters["contains_character"] = m.group(1)
            
    # Heuristic for "first vowel" from instructions
    if "first vowel" in lower and "contains_character" not in filters:
        filters["contains_character"] = "a" 
        
    # 400 Bad Request if no filters were successfully parsed
    if not filters:
        raise HTTPException(status_code=400, detail="Unable to parse natural language query")
        
    return {"parsed_filters": filters, "original": query}

# 4. Natural Language Filtering (GET /strings/filter-by-natural-language)
@app.get("/strings/filter-by-natural-language")
def filter_by_natural_language(query: str):
    parsed_data = parse_natural_language(query)
    filters = parsed_data["parsed_filters"]
    
    results = []
    for record in db.values():
        prop = record["properties"]
        
        # Apply parsed filters (word_count, is_palindrome, min_length, contains_character)
        if "is_palindrome" in filters and prop["is_palindrome"] != filters["is_palindrome"]:
            continue
        if "min_length" in filters and prop["length"] < filters["min_length"]:
            continue
        if "word_count" in filters and prop["word_count"] != filters["word_count"]:
            continue
            
        # Check character inclusion using the frequency map
        if "contains_character" in filters:
            if filters["contains_character"] not in prop["character_frequency_map"]:
                continue
                
        results.append(record)
        
    # Return count and interpreted query object as required
    return {
        "data": results,
        "count": len(results),
        "interpreted_query": parsed_data
    }

# 5. Delete String (DELETE /strings/{string_value})
@app.delete("/strings/{string_value}", status_code=204)
def delete_string(string_value: str):
    record = find_string_record(string_value)
    
    # 404 Not Found check
    if not record:
        raise HTTPException(status_code=404, detail="String not found")
        
    # Delete from in-memory DB
    del db[record["id"]]
    # 204 No Content is returned automatically by FastAPI for a successful None return with status_code=204
    return None

# Health Check (NEW)
@app.get("/health")
def health_check():
    """
    Standard health check endpoint required for deployment monitoring.
    Returns 200 OK if the service is running.
    """
    return {"status": "ok"}
    

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)    
    
