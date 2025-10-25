from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, validator
from typing import Optional, Dict, List
from hashlib import sha256
from datetime import datetime
import re

app = FastAPI()

# In-memory store for strings keyed by sha256 hash
db = {}

class StringInput(BaseModel):
    value: str

    @validator('value')
    def non_empty_string(cls, v):
        if not isinstance(v, str):
            raise ValueError("Must be a string")
        if v == "":
            raise ValueError("Value cannot be empty")
        return v

def analyze_string(s: str) -> Dict:
    lower = s.lower()  # Case-insensitive palindrome check
    length = len(s)
    is_palindrome = lower == lower[::-1]
    unique_characters = len(set(s))
    word_count = len(s.split())
    hash_value = sha256(s.encode()).hexdigest()
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

@app.post("/strings", status_code=201)
def create_string(input: StringInput):
    # Value is guaranteed to exist and be string by validator, else Pydantic returns 422 automatically

    # Check if string already exists by hash
    props = analyze_string(input.value)
    if props["sha256_hash"] in db:
        raise HTTPException(status_code=409, detail="String already exists")

    # Prepare record
    now_iso = datetime.utcnow().isoformat() + "Z"
    record = {
        "id": props["sha256_hash"],
        "value": input.value,
        "properties": props,
        "created_at": now_iso
    }

    db[props["sha256_hash"]] = record
    return record

def find_string_record(s: str):
    hash_value = sha256(s.encode()).hexdigest()
    return db.get(hash_value)

@app.get("/strings/{string_value}")
def get_string(string_value: str):
    record = find_string_record(string_value)
    if not record:
        raise HTTPException(status_code=404, detail="String not found")
    return record

@app.get("/strings")
def get_all_strings(
    is_palindrome: Optional[bool] = Query(None),
    min_length: Optional[int] = Query(None, ge=0),
    max_length: Optional[int] = Query(None, ge=0),
    word_count: Optional[int] = Query(None, ge=0),
    contains_character: Optional[str] = Query(None, min_length=1, max_length=1)
):
    results = []
    for record in db.values():
        prop = record["properties"]
        if is_palindrome is not None and prop["is_palindrome"] != is_palindrome:
            continue
        if min_length is not None and prop["length"] < min_length:
            continue
        if max_length is not None and prop["length"] > max_length:
            continue
        if word_count is not None and prop["word_count"] != word_count:
            continue
        if contains_character is not None and contains_character not in record["value"]:
            continue
        results.append(record)
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
    return {
        "data": results,
        "count": len(results),
        "filters_applied": filters_applied
    }

def parse_natural_language(query: str) -> Dict:
    lower = query.lower()
    filters = {}

    if "single word" in lower or "one word" in lower:
        filters["word_count"] = 1
    if "palindromic" in lower or "palindrome" in lower:
        filters["is_palindrome"] = True
    if "strings longer than" in lower:
        m = re.search(r"strings longer than (\d+)", lower)
        if m:
            filters["min_length"] = int(m.group(1)) + 1
    if "containing the letter" in lower:
        m = re.search(r"containing the letter (\w)", lower)
        if m:
            filters["contains_character"] = m.group(1)
    if not filters:
        raise HTTPException(status_code=400, detail="Unable to parse natural language query")
    return filters

@app.get("/strings/filter-by-natural-language")
def filter_by_natural_language(query: str):
    filters = parse_natural_language(query)
    results = []
    for record in db.values():
        prop = record["properties"]
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
    return {
        "data": results,
        "count": len(results),
        "interpreted_query": {
            "original": query,
            "parsed_filters": filters
        }
    }

@app.delete("/strings/{string_value}", status_code=204)
def delete_string(string_value: str):
    record = find_string_record(string_value)
    if not record:
        raise HTTPException(status_code=404, detail="String not found")
    del db[record["id"]]
    return None

    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
        
    
    
