import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry

url1 = "https://api.open-meteo.com/v1/forecast"
url2 = "https://marine-api.open-meteo.com/v1/marine"


cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)

max_score_tolerance = 0.5 # plus on augmente ce nombre, plus il y aura d'horaires pouvant convenir
tolerance_step = 0.5 # par combien on va augmenter la tolerance a chaque probleme

min_wave_height = 0.4
max_wave_height = 3
min_wave_period = 6
max_wave_period = 14
min_wind_speed = 40
max_wind_speed = 15
beach_direction = 45

# Source - https://stackoverflow.com/a/70659904
# Posted by CrazyChucky, modified by community. See post 'Timeline' for change history
# Retrieved 2026-07-08, License - CC BY-SA 4.0
def map_range(x, in_min, in_max, out_min, out_max):
  return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min

# vient de chatgpt
def compare_arrays(arr):
    result = set(arr[0]) # on transforme la permiere liste en ensemble
    for i in arr[1:]: # on loop chaque liste en entree
        result &= set(i) # on garde que les valeurs communes avec celle d'avant
    return list(result)

def requests_forecast():
    #  (1) first request: wind direction and speed
    params = {
        "latitude": 47.9549,
        "longitude": -4.3605,
        "hourly": ["wind_speed_10m", "wind_direction_10m"],
        "timezone": "auto",
        "forecast_days": 1,
    }
    responses = openmeteo.weather_api("https://api.open-meteo.com/v1/forecast", params)
    response = responses[0]
    hourly = response.Hourly()
    hourly_wind_speed = hourly.Variables(0).ValuesAsNumpy()
    hourly_wind_direction = hourly.Variables(1).ValuesAsNumpy()
    
    #  (2) second:  wave height, wave direction, wave direction
    params = {
        "latitude": 47.9549,
        "longitude": -4.3605,
        "hourly": ["wave_height", "wave_period"],
        "timezone": "auto",
        "forecast_days": 1,
    }
    responses = openmeteo.weather_api("https://marine-api.open-meteo.com/v1/marine", params)
    response = responses[0]
    hourly = response.Hourly()
    hourly_wave_height = hourly.Variables(0).ValuesAsNumpy()
    hourly_wave_period = hourly.Variables(1).ValuesAsNumpy()

    # (3) return the result
    # [[wind speed], [wind direction], [wave height], [wave period]]
    return [hourly_wind_speed, hourly_wind_direction, hourly_wave_height, hourly_wave_period]



def score_data(data, type): 
    # cette fonction sert a noter une donnees de type: vitese vent, diretion vent, etc
    # 0: c'est nul, sinon le score est entre 1 et 10
    # type -> 0: vitesse vent, 1: direction vent, 2: hauteur vagues, 3: periode vague
    
    score = 0
    if type == 0:
        if data <= max_wind_speed:
            score = 10
        else:
            if data <= min_wind_speed:
                score = map_range(data, min_wind_speed, max_wind_speed, 1, 10)
            else:
                score = 0
    elif type == 1:
        # analyse vient de chatgpt
        diff = abs(data - beach_direction) # calcul l'ecart entre la direction de la plage et le vent
        diff = min(diff, 360 - diff) # calcul le vrai ecart (car 45 et 355 ne sont pas loin par exemple )
        score = 10 - 9 * (diff / 180) 
    elif type == 2:
        if data >= min_wave_height and data <= max_wave_height:
            score = map_range(data, min_wave_height, max_wave_height, 1, 10)
        else:
            score = 0
    elif type == 3:
        if data >= min_wave_period and data <= max_wave_period:
            score = map_range(data, min_wave_period, max_wave_period, 1, 10)
        else:
            score = 0
    return score
     

def get_dicts(tolerance):
    # on recup les tableaux pour chaque categories avec requests_forecast(),
    # on analyse ces donnees et on fait des dict qui contiennent toutes les donnees
    # importantes de la categorie, comme le score moyen, le score max et poru quelles heures, etc

    current_dict = {} # le dict qu'on va remplir

    # les dict finaux
    wave_height_dict = {}
    wave_period_dict = {}
    wind_speed_dict = {}
    wind_dir_dict = {}
    

    categ = requests_forecast() # on recupere les 4 tableaux des categories
    current = 0 # pour savoir sur qu'elle ccategories on est actuellement
    # rappel -> 0: vitesse vent, 1: direction vent, 2: hauteur vagues, 3: periode vague
    for i in categ: # boucle 4 fois, i sera le tableau a analyser
        
        hour = 0
        max_score = 0
        scores = [] # va contenir tous les scores
        total_score = 0 # to do average score
        total_data = 0 # to do average data

        for u in i: # boucle chaque heure de la categories
            
            current_score =  score_data(u, current) # on score la donnee
            scores.append(current_score)
            max_score = max(max_score, current_score) # on verifie le score
            total_score += current_score
            total_data += u
            hour += 1


        average_score = float(total_score) / 24
        average_data = float(total_data) / 24

        if max_score:
            # vient de chatgpt, on regarde l'index (l'heure) ou le meilleur score -1 est atteint
            index_max_score = [i for i, val in enumerate(scores) if val > max_score - tolerance]
        else:
            index_max_score = [0]

        current_dict = {
            "type": current,
            "data": i,
            "scores": scores,
            "max_score": max_score,
            "average_score": average_score,
            "average_data": average_data,
            "best_hours": index_max_score
        } 

        if current == 0:
            wind_speed_dict = current_dict
        elif current == 1:
            wind_dir_dict = current_dict
        elif current == 2:
            wave_height_dict = current_dict 
        elif current == 3:
            wave_period_dict = current_dict 

        current += 1

    return wind_speed_dict, wind_dir_dict, wave_height_dict, wave_period_dict



def main():
    # fonc generale : recupere, analyse, compare, deduis, transmet

    current_tolerance = max_score_tolerance
    result = { # va etre remplie dans le code pour etre transmise a ntfy
        "title": "",
        "content": "",
        "tags": ""
    }
    
    
    # 1) on analyse les donnees une premiere fois
    dicts = get_dicts(current_tolerance)

    # 2) on verif si les conditions peuvent convenir (si max score != 0)
    dict_speed = dicts[0]
    dict_dir = dicts[1]
    dict_height = dicts[2]
    dict_period = dicts[3]
    
    # si une des categ n'a que des 0 comme score, on arrete le programme, on ne peut pas faire de surf
    test = dict_speed["max_score"] * dict_dir["max_score"] * dict_height["max_score"] * dict_period["max_score"]
    print("Test: ", test)
    if not test:
        # une des categ est nulle, on determine laquelle avant d'envoyer la reponse
        result["title"] = "Pas aujourd'hui pour le surf"
        result["tags"] = "warning"
        bad_categ = "En effet, "
        if not dict_speed["max_score"]:
            bad_categ += f"le vent depasse les {round(dict_speed['average_data'], 2)}km/h."
        if not dict_dir["max_score"]:
            bad_categ += f"en moyenne, la direction du vent est de {round(dict_dir['average_data'], 2)} degres."
        if not dict_height["max_score"]:
            bad_categ += f"la moyenne des vagues ne depasse pas les {round(dict_height['average_data'], 2)}m."
        if not dict_period["max_score"]:
            bad_categ += f"la periode de vague est de {round(dict_period['average_data'], 2)}s."
        result["content"] = bad_categ
        return result
    else:

        selected_hours = []
        i = 0
        while True:
            best_hours = [
                dict_speed["best_hours"],
                dict_dir["best_hours"],
                dict_height["best_hours"],
                dict_period["best_hours"]
            ]
            selected_hours = compare_arrays(best_hours)
            if selected_hours:
                break

            # tant qu'on na pas d'horaires on baisse la tolerance
            current_tolerance += tolerance_step
            dicts = get_dicts(current_tolerance)
            dict_speed = dicts[0]
            dict_dir = dicts[1]
            dict_height = dicts[2]
            dict_period = dicts[3]
    

            i += 1
        result["title"] = "Une petite session de surf ?"
        result["content"] = f"Avec une tolerance de {int(current_tolerance)}, les meilleurs heures sont: "
        result["content"] += "h, ".join(map(str, selected_hours)) + "h"
        result["content"] += ". Voici un apercu des donnees analysee, en moyenne: \n"
        result["content"] += f"Vitesse du vent: {round(dict_speed['average_data'], 2)}km/h, score: {round(dict_speed['average_score'], 2)}."
        result["content"] += f" Ecart du vent: {round(dict_dir['average_data'], 2)} degres, score: {round(dict_dir['average_score'], 2)}."
        result["content"] += f" Hauteur des vagues: {round(dict_height['average_data'], 2)}m, score: {round(dict_height['average_score'], 2)}."
        result["content"] += f" Periode des vagues: {round(dict_period['average_data'], 2)}s, score: {round(dict_period['average_score'], 2)}."
        return result

print(main())
# print("-------")
# for key, value in dicts[0].items():
#     print(f"{key}: {value}")
# print("-------")
# for key, value in dicts[1].items():
#     print(f"{key}: {value}")
# print("-------")
# for key, value in dicts[2].items():
#     print(f"{key}: {value}")
# print("-------")
# for key, value in dicts[3].items():
#     print(f"{key}: {value}")