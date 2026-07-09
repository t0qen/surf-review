import openmeteo_requests

import pandas as pd
import requests_cache
from retry_requests import retry

url1 = "https://api.open-meteo.com/v1/forecast"

url2 = "https://marine-api.open-meteo.com/v1/marine"


cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)

min_wave_height = 0.7
max_wave_height = 3
min_wave_period = 6
max_wave_period = 16
min_wind_speed = 40
max_wind_speed = 15
beach_direction = 45

# Source - https://stackoverflow.com/a/70659904
# Posted by CrazyChucky, modified by community. See post 'Timeline' for change history
# Retrieved 2026-07-08, License - CC BY-SA 4.0
def map_range(x, in_min, in_max, out_min, out_max):
  return (x - in_min) * (out_max - out_min) // (in_max - in_min) + out_min


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
    # score a data from for example hourly_wind_speed[6], in that case type would be "speed"
    # score 0 : so bad; score 1-10

    score = 0
    match type:
        case "speed":
            if data <= max_wind_speed:
                score = 10
            else:
                if data <= min_wind_speed:
                    score = map_range(data, min_wind_speed, max_wind_speed, 1, 10)
                else:
                    score = 0

        case "dir":
            # from chatgpt (i genually couldnt find a way do it otherway)
            diff = abs(data - beach_direction)
            diff = min(diff, 360 - diff) # bec for example 350 isnt far from 45
            score = 10 - 10 * (diff / 180) # linear interpolation, makes a difference in degres to a score between 1 and 10
            
        case "height":
            if data >= min_wave_height and data <= max_wave_height:
                score = map_range(data, min_wave_height, max_wave_height, 1, 10)
            else:
                score = 0

        case "period":
            if data >= min_wave_period and data <= max_wave_period:
                score = map_range(data, min_wave_period, max_wave_period, 1, 10)
            else:
                score = 0


    return score
     
# test = requests_forecast()
# scored = [2]

# for i in test[3]:
#     print(i)
#     scored[0] = score_data(i, "period")
#     print(" Score : ", scored[0])
#     # scored[1] = test[i]
#     # print("Data : ", scored[1], " Score : ", scored[0])

def get_best_score_per_hours():
    # loop array from requests_forecast(), get their score with score_data() 
    # and determine the hour of the day 
    categ = requests_forecast() # categ = category
    print(categ)
    current = 0 # counter to not forgot which unite 
    for i in categ: # loop 4 times, score all unites
        if current == 0:
            current_categ = "speed"
        elif current == 1:
            current_categ = "dir"
        elif current == 2:
            current_categ = "height"
        else:
            current_categ = "period"
        print("-- Current categ: ", current_categ)
        
        hour = 0
        for u in i:
            hour += 1
            print("Hour: ", hour)
            print("Data: ", u)
            print("Score: ", score_data(u, current_categ))
        
        
        current += 1
get_best_score_per_hours()