import argparse
import time
import json
import requests
import os

logs = []
logtofile = True
try:
    def logger(message: str,place: str,name: str, colorid : int=39):
        match colorid:
            case 31: log_type = 'ERROR'
            case 32: log_type = 'SUCCESS'
            case 33: log_type = 'WARN'
            case _: log_type = 'INFO'
            
        log = f'[{time.strftime('%H:%M:%S', time.localtime())}][{place}/{log_type}][{name}]: {message}'
        if verbose:
            print(f'\033[{colorid}m'+log+'\033[0m')
        if logtofile:
            logs.append(log+'\n')

    class main:
        def __init__(self, name : str, authorization : str):
            self.authorization = authorization
            self.api = 'https://api.cloudflare.com/client/v4/'
            self.headers ={'Authorization' : f'Bearer {self.authorization}'}
            self.zone_id = ''
            self.record_id = ''
            self.payload = ''
            self.already_matching = []
            self.name = name 
            self.get_ip()

                
        def get_ip(self):
            place = 'Get IP'
            logger('Attempting to fetch IP',place,self.name)
            response = requests.get('https://checkip.amazonaws.com/')

            if response.ok:
                self.ip = response.content[:-1].decode('utf-8')
                logger(f'IP was succesfully fetched {self.ip}',place,self.name,32)
                return(True)
            logger(f'IP was not fetched status: {response.status_code}, {response.content}',place,self.name,31)
            return(False)

        def find_zone(self):
            place = 'Zone Finder'
            url = f'{self.api}/zones'
            name = self.name.split('.')
            
            logger('Fetching zones',place,self.name)
            
            response = requests.get(url=url,headers=self.headers)
            
            if response.ok:
                zones = json.loads(response.content)
                
                if zones['success']:
                    logger('Zones fetched',place,self.name,32)
                    for zone in zones['result']:
                        current_name = zone['name'].split('.')
                        domain_list = name[-len(current_name):]
                        
                        domain = ''
                        for x in domain_list:
                            domain += '.' + x
                        domain = domain[1:]
                        

                        if domain == zone['name']:
                            self.zone_id = zone['id']
                            logger(f'Zone found {self.zone_id}',place,self.name,32)
                            break
                    return(True)
            logger('Failed to fetch zones',place,self.name,31)
            return(False)
        
        def find_record(self):
            place = 'Record Finder'
            url = f'{self.api}/zones/{self.zone_id}/dns_records'
            
            logger('Fetching records',place,self.name)
            
            response = requests.get(url=url,headers=self.headers)
            
            
            if response.ok:
                records = json.loads(response.content.decode('utf-8'))
                if records['success']:
                    logger('Records fetched.',place,self.name,32)
                    for record in records['result']:
                        if record['name'] == self.name:
                            if record['content'] == self.ip:
                                self.already_matching.append(record['name'])
                                logger(f'Matching record found but content already matches current IP address {self.ip}',place,self.name,33)
                                break
                            else:
                                self.record_id = record['id']
                                logger(f'Matching record found {self.record_id}',place,self.name,32)
                                break
                    return(True)
            logger('Failed to fetch records',place,self.name,31)
            return(False)

        def construct_payload(self):
            place = 'Payload Constructor'
            if not(self.ip):
                logger('IP address not found',place,self.name,31)
                self.get_ip()
                return(False)
            self.payload = {
                'name': self.name,
                'ttl': 1,
                'type': 'A',
                'content': self.ip,
                'proxied': False
                }
            return(True)

        def create_record(self):
            place = 'Record Creator'
            url = f'{self.api}/zones/{self.zone_id}/dns_records'
            
            headers = self.headers.copy()
            headers['Content-Type'] = 'application/json'
            
            logger(f'Creating record {self.name} with {self.ip}',place,self.name)
            
            if self.construct_payload():
                response = requests.post(url, headers=headers, json=self.payload)
                return(response.ok)
            return(False)

        def update_record(self):
            place = 'Record Updater'
            url = f'{self.api}/zones/{self.zone_id}/dns_records/{self.record_id}'
            
            headers = self.headers.copy()
            headers['Content-Type'] = 'application/json'
            
            logger(f'Updating record {self.name} with {self.ip}',place,self.name)
            if self.construct_payload():
                response = requests.patch(url, headers=headers, json=self.payload)
                return(response.ok)
            return(False)
        
        
    parser = argparse.ArgumentParser(
                    prog='simple-cloudflare-ddns',
                    description='Automatically creates or modifies given cloudflare record(s) with the external IP address.'
    )

    parser.add_argument('-A', '--authorization',type=str, required=True)
    parser.add_argument('-n', '--names',nargs='+',required=True)
    parser.add_argument('-t','--tries',type=int,default=3)
    parser.add_argument('-v','--verbose',action='store_true',default=False)
    parser.add_argument('-l','--logtofile',action='store_true',default=False)

    args = parser.parse_args()

    authorization = args.authorization
    names = args.names
    tries = args.tries
    verbose = args.verbose
    logtofile = args.logtofile



    for name in names:
        place = 'Attempter'
        session = main(name,authorization)        
        for attempt in range(1,tries+1):
            logger(f'Attempt {attempt}/{tries}',place,name)
            if session.find_zone() and session.zone_id:
                logger(f'Zone ID {session.zone_id}',place,name)
                if session.find_record() and session.record_id:
                    logger(f'Record ID {session.record_id}',place,name)
                    if session.update_record():
                        logger(f'Record updated with IP address {session.ip}',place,name,32) 
                        break
                elif name in session.already_matching:
                    logger(f'Record already matches current IP address {session.ip}, skipping.',place,name,32)    
                    break                
                else:
                    if session.create_record():
                        logger(f'Record created with IP address {session.ip}',place,name,32)
                        break
            logger(f'Attempt {attempt} Failed',place,name,31)
            time.sleep(5)
finally:
    if logtofile:
        log_files = []
        for file_name in os.listdir():
            if file_name.startswith("cf_ddns_"):
                log_files.append(file_name)
            log_files.sort()
            for log_file in log_files[5:]:
                os.remove(log_file)
                
        with open(f'cf_ddns_{int(time.time())}.log','w') as f:
            f.writelines(logs)
            
