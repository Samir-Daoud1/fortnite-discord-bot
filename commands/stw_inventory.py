import requests
import json
import os
import sys

# API Endpoint for Save the World items
STW_API_ITEMS_URL = "https://fortnite-api.com/v2/stw/items"

# --- EXCLUSION LISTS ---
# These are kept minimal to truly aim for "every single item" that is relevant.
# They primarily target internal dev tools, pure BR-related IDs, or redundant/abstract entries.

# Prefixes of template IDs to exclude (e.g., specific internal dev items, or generic BR cosmetic types)
# Re-evaluating based on "EVERY SINGLE ITEM" request:
# We will be very selective here. Building data is typically not managed in inventory.
EXCLUDED_ITEM_PREFIXES = (
    "Weapon:buildingitemdata_", # Excludes generic building pieces like walls, floors, roofs
    "AccountResource:currency_", # Excludes abstract currencies, which are not "items" in inventory sense
)

# Specific full template IDs to exclude (e.g., internal tools, very specific BR-only data that might slip in)
EXCLUDED_ITEM_IDS = set([
    "Weapon:edittool", # Internal editor tool, not a game item
    # Add other specific, known irrelevant IDs as you discover them if they pass prefixes
    # For example, if you find "Consumable:some_br_only_consumable" that's not relevant to STW
])

# --- ITEM NAMING AND IMAGE RETRIEVAL ---

# Define a map for specific template IDs where the API's name might be less intuitive,
# or for common resources/ammo to give them standard display names.
ITEM_NAME_OVERRIDE_MAP = {
    # Basic Resources (often have WorldItem: prefix, but can be explicitly named)
    "WorldItem:wooditemdata": "Wood",
    "WorldItem:stoneitemdata": "Stone",
    "WorldItem:metalitemdata": "Metal",
    # Ammo Types
    "Ammo:ammo_assault_rifle_t01": "Light Ammo",
    "Ammo:ammo_shotgun_t01": "Shells 'n' Slugs",
    "Ammo:ammo_sniper_t01": "Sniper Ammo",
    "Ammo:ammo_pistol_t01": "Light Ammo", # Pistol ammo often shares with AR
    "Ammo:ammo_rocket_t01": "Rocket Ammo",
    "Ammo:ammo_energycell_t01": "Energy Cells",
    # Common Ingredients (if API name isn't ideal)
    "Ingredient:ingredient_ducttape": "Duct Tape",
    "Ingredient:ingredient_mechanical_parts_t05": "Efficient Mechanical Parts",
    "Ingredient:ingredient_ore_brightcore": "Brightcore Ore",
    "Ingredient:ingredient_rare_powercell": "Power Cells",
    # Add more as you discover them
}


def get_item_display_name(template_id: str, api_name: str) -> str:
    """
    Determines the display name for an item.
    Prioritizes ITEM_NAME_OVERRIDE_MAP, then API's provided name, then parses from templateId.
    """
    if template_id in ITEM_NAME_OVERRIDE_MAP:
        return ITEM_NAME_OVERRIDE_MAP[template_id]
    
    if api_name:
        return api_name

    # Fallback: try to parse from templateId if no direct name or override
    parts = template_id.split(':')
    if len(parts) > 1:
        clean_name = parts[-1]
        # Remove common tier/rarity suffixes from template IDs for cleaner names
        clean_name = clean_name.replace('_sr_t05', '').replace('_t05', '').replace('_t04', '').replace('_t03', '').replace('_t02', '').replace('_t01', '')
        # Convert snake_case to Title Case
        clean_name = ' '.join(word.capitalize() for word in clean_name.split('_'))
        return clean_name
    return template_id # As a last resort, return the raw template ID


def get_item_image_url(item_data: dict) -> str | None:
    """
    Extracts the most suitable image URL from item_data.
    Checks for 'icon', 'fullBackground', 'background' in order of preference.
    """
    images = item_data.get('images', {})
    return images.get('icon') or images.get('fullBackground') or images.get('background')


def generate_full_stw_database(output_file: str = 'public/stw_full_database.json'):
    """
    Fetches all Save the World items from Fortnite-API.com, processes them,
    and saves them to a JSON file.
    """
    print(f"Attempting to fetch all STW items from {STW_API_ITEMS_URL}...")
    try:
        response = requests.get(STW_API_ITEMS_URL)
        response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        
        processed_items = []
        
        if data and data.get('status') == 200 and data.get('data'):
            for item in data['data']:
                template_id = item.get('templateId')
                
                # Apply exclusions
                if template_id in EXCLUDED_ITEM_IDS:
                    continue
                
                should_exclude_by_prefix = False
                for prefix in EXCLUDED_ITEM_PREFIXES:
                    if template_id.startswith(prefix):
                        should_exclude_by_prefix = True
                        break
                if should_exclude_by_prefix:
                    continue

                # Get item details
                item_name = get_item_display_name(template_id, item.get('name'))
                item_image_url = get_item_image_url(item)
                item_rarity = item.get('rarity', {}).get('displayValue', 'Common')
                item_type = item.get('type', {}).get('displayValue', 'Unknown Type')
                item_description = item.get('description', '')

                processed_items.append({
                    "templateId": template_id,
                    "name": item_name,
                    "description": item_description,
                    "rarity": item_rarity,
                    "type": item_type,
                    "imageUrl": item_image_url
                })
            
            # Sort items by name for consistent output
            processed_items.sort(key=lambda x: x['name'].lower())

            # Ensure the output directory exists
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)

            # Save the processed items to a JSON file
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(processed_items, f, ensure_ascii=False, indent=2)
            
            print(f"Successfully generated STW full database JSON: {output_file}")
            print(f"Total unique items processed and saved: {len(processed_items)}")
        else:
            print(f"API response indicates failure or no data: Status {data.get('status')}, Error: {data.get('error')}")
            sys.exit(1) # Exit with an error code

    except requests.exceptions.RequestException as e:
        print(f"Network error during API request: {e}")
        print("Please check your internet connection and the API URL.")
        sys.exit(1) # Exit with an error code
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from API response: {e}")
        print("The API might have returned invalid JSON. Try again later.")
        sys.exit(1) # Exit with an error code
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1) # Exit with an error code

if __name__ == '__main__':
    # Run the function to generate the database.
    # This will create 'public/stw_full_database.json' in your current working directory.
    # Make sure this 'public' directory is accessible by your web server/React app.
    generate_full_stw_database()