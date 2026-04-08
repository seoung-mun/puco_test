def get_action_text(action: int) -> str:
    if 0 <= action <= 7:
        roles = ["Settler", "Mayor", "Builder", "Craftsman", "Trader", "Captain", "Prospector 1", "Prospector 2"]
        return f"Select Role: {roles[action]}"
    elif 8 <= action <= 13:
        return f"Settler: Take Face-up Plantation #{action - 8 + 1}"
    elif action == 14:
        return "Settler: Take Quarry"
    elif action == 15:
        return "Pass / End Turn"
    elif 16 <= action <= 38:
        buildings = [
            "Small Indigo Plant", "Small Sugar Mill", "Indigo Plant", "Sugar Mill", 
            "Tobacco Storage", "Coffee Roaster", "Small Market", "Hacienda", 
            "Construction Hut", "Small Warehouse", "Hospice", "Office", 
            "Large Market", "Large Warehouse", "Factory", "University", 
            "Harbor", "Wharf", "Guildhall", "Residence", "Fortress", 
            "Customs House", "City Hall"
        ]
        return f"Builder: Build {buildings[action - 16]}"
    elif 39 <= action <= 43:
        goods = ["Coffee", "Tobacco", "Corn", "Sugar", "Indigo"]
        return f"Trader: Sell {goods[action - 39]}"
    elif 44 <= action <= 58:
        idx = action - 44
        ship_idx = idx // 5
        good_idx = idx % 5
        goods = ["Coffee", "Tobacco", "Corn", "Sugar", "Indigo"]
        return f"Captain: Load {goods[good_idx]} on Ship #{ship_idx + 1}"
    elif 59 <= action <= 63:
        goods = ["Coffee", "Tobacco", "Corn", "Sugar", "Indigo"]
        return f"Captain: Load {goods[action - 59]} via Wharf"
    elif 64 <= action <= 68:
        goods = ["Coffee", "Tobacco", "Corn", "Sugar", "Indigo"]
        return f"Captain Store: Keep {goods[action - 64]} on Windrose"
    elif 69 <= action <= 72:
        return f"Mayor: Place {action - 69} Colonist(s)"
    elif 93 <= action <= 97:
        goods = ["Coffee", "Tobacco", "Corn", "Sugar", "Indigo"]
        return f"Craftsman: Extra Production of {goods[action - 93]}"
    elif action == 105:
        return "Settler: Blind Draw (Hacienda)"
    elif 106 <= action <= 110:
        goods = ["Coffee", "Tobacco", "Corn", "Sugar", "Indigo"]
        return f"Captain Store: Keep {goods[action - 106]} in Warehouse"
    else:
        return f"Unknown Action ({action})"

def get_good_name(good_id: int) -> str:
    goods = ["Coffee", "Tobacco", "Corn", "Sugar", "Indigo", "None"]
    return goods[good_id] if 0 <= good_id <= 5 else str(good_id)

def get_tile_name(tile_id: int) -> str:
    tiles = ["Coffee", "Tobacco", "Corn", "Sugar", "Indigo", "Quarry", "Empty"]
    return tiles[tile_id] if 0 <= tile_id < len(tiles) else str(tile_id)

def get_building_name(building_id: int) -> str:
    buildings = [
        "Small Indigo Plant", "Small Sugar Mill", "Indigo Plant", "Sugar Mill", 
        "Tobacco Storage", "Coffee Roaster", "Small Market", "Hacienda", 
        "Construction Hut", "Small Warehouse", "Hospice", "Office", 
        "Large Market", "Large Warehouse", "Factory", "University", 
        "Harbor", "Wharf", "Guildhall", "Residence", "Fortress", 
        "Customs House", "City Hall", "Empty", "Occupied Space"
    ]
    return buildings[building_id] if 0 <= building_id < len(buildings) else str(building_id)

def get_phase_name(phase_id: int) -> str:
    phases = [
        "SETTLER", "MAYOR", "BUILDER", "CRAFTSMAN", "TRADER", 
        "CAPTAIN", "CAPTAIN_STORE", "PROSPECTOR", "END_ROUND", "INIT"
    ]
    return phases[phase_id] if 0 <= phase_id < len(phases) else str(phase_id)
