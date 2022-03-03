import pickle
import os
import socket
from time import strftime
import json
 
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
from oauth2client.service_account import ServiceAccountCredentials
import gspread
 
import thermalcamera
import findIP
 
UNIT_OFFSET = 1
CRED_DIR = '/home/pi/iow/credentials.json'
IMG_DIR = '/home/pi/iow/images/'
WEB_DIR = '/home/pi/iow/static/images/'
device = '/dev/spidev0.0'
ID_DIR = '/home/pi/iow/unitDetails.json'
IMAGE_DIR = '/home/pi/iow/imageDetails.json'
 
def checkUnitID():
    if not os.path.isfile(ID_DIR):
        with open(ID_DIR, 'a') as outfile:
            json.dump(data, outfile)
    with open(ID_DIR) as json_file:
        data = json.load(json_file)
        for p in data['device']:
            deviceID = p['unitID']
            folder_id = p['Folder ID']
            bt1State = p['bt1State']
            bt2State = p['bt2State']
            return(deviceID,folder_id, bt1State, bt2State)
 
def update_json(unitID, folderID):
    with open(ID_DIR) as json_file:
        data = json.load(json_file)
        data['device'][0]['unitID'] = unitID
        data['device'][0]['Folder ID'] = folderID
        print("New Connection: unit_{0}".format(unitID))
    with open(ID_DIR, 'w') as outfile:
        json.dump(data, outfile)
 
def update_json_image(time, date, maxB, minB):
    with open(IMAGE_DIR) as json_file:
        data = json.load(json_file)
        data['imageDetails'][0]['time'] = time
        data['imageDetails'][0]['date'] = date
        data['imageDetails'][0]['maxV'] = maxB
        data['imageDetails'][0]['minV'] = minB
    with open(IMAGE_DIR, 'w') as outfile:
        json.dump(data, outfile)
 
def checkDetails(unit):
    creds = gspread.service_account(
        filename=CRED_DIR)
    sh = creds.open("DeviceList").sheet1
    unit = unit + UNIT_OFFSET
    endCell = unit + 13
    readID = sh.get('H{0}:H{1}'.format(unit,endCell))
    readUse = sh.get('I{0}:I{1}'.format(unit,endCell))
    return(readID,readUse)
 
def serviceAccountCreds():
    #Set up a credentials
    creds = ServiceAccountCredentials.from_json_keyfile_name(CRED_DIR, ['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=creds)
 
def measure_temp():
    cpu = os.popen("vcgencmd measure_temp").readline()
    cpu = cpu.replace("temp=", "")
    cpu = cpu.replace("'C", "")
    cpu = cpu.rstrip("\n")
    return(cpu)
 
def uploadFile(fileName, folder_id, type):
    service = serviceAccountCreds()
    file_metadata = {
        "name": '{0}'.format(fileName),
        "parents": [folder_id]
    }
    print('{0}{1}'.format(IMG_DIR, fileName))
    media = MediaFileUpload('{0}{1}'.format(IMG_DIR, fileName), resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print("File created, id:", file.get("id"))
    return('{0}: ok, '.format(type))
 
def updateSheet(unit, ip, googlestamp, cpu, log, status):
    unit = int(unit) + 1
    creds = gspread.service_account(
        filename=CRED_DIR)
    sh = creds.open("DeviceList").sheet1
    sh.update('B{0}'.format(unit), 'http://{0}:5000'.format(ip))
    sh.update('C{0}'.format(unit), '{0}'.format(googlestamp))
    sh.update('D{0}'.format(unit), '{0}'.format(cpu))
    sh.update('E{0}'.format(unit), '{0}'.format(log))
    sh.update('F{0}'.format(unit), '{0}'.format(status))
 
def updatelog(unit, ip, googlestamp, cpu, log, status):
    unit = int(unit)
    creds = gspread.service_account(
        filename=CRED_DIR)
    sh = creds.open("log")
    sheet = int(unit) - 1   #sheet starts at 0
    ws = sh.get_worksheet(sheet)
    data = [unit, 'http://{0}:5000'.format(ip), '{0}'.format(googlestamp),'{0}'.format(cpu),'{0}'.format(log), status]
    ws.insert_row(data, index=2, value_input_option='USER_ENTERED')
 
def cleanFolder(folder, cap):
    path = folder
    max_Files = cap
    def sorted_ls(path):
        mtime = lambda f: os.stat(os.path.join(path, f)).st_mtime
        return list(sorted(os.listdir(path), key=mtime))
    del_list = sorted_ls(path)[0:(len(sorted_ls(path))-max_Files)]
    for dfile in del_list:
        os.remove(path + dfile)
 
def main(source, sourceState):
    unitID, folder_id, bt1State, bt2State = checkUnitID()
    print(unitID, folder_id)
    if unitID == "0":
        idResults, useResults = checkDetails(1)
        for x in range(0,13):
            if useResults[x][0] == 'Free':
                #print("loop number: {0}".format(x))
                #print("usage: {0}".format(useResults[x][0]))
                #print("idTag: {0}".format(idResults[x][0]))
                update_json(str(x+1), idResults[x][0])
                unitID = x + 1
                folder_id = idResults[x][0]
                creds = gspread.service_account(
                    filename=CRED_DIR)
                sh = creds.open("DeviceList").sheet1
                sh.update('I{0}'.format(x+2), 'Taken')
                break
            else:
                pass
    else:
        pass
    print(unitID, folder_id)
   
    stamp = strftime("%d%m%y-%H%M%S")
    googlestamp = strftime("%d/%m/%y %H:%M:%S")
    timeStamp = strftime("%H:%M:%S")
    dateStamp = strftime("%d/%m/%y")
    log = ""
    imageName = ""
    try:
        imageName, csvName, maxV, minV, status= thermalcamera.main(IMG_DIR, WEB_DIR, device, stamp)
        update_json_image(timeStamp,dateStamp,maxV,minV)
        print("imageName: {0}".format(imageName))
        print("csvName: {0}".format(csvName))
        if imageName != 'failure':
            log = log + uploadFile(imageName, folder_id, 'png')
        else:
            log = "pngUpload: ng, "
        if csvName != 'failure':
            log = log + uploadFile(csvName, folder_id, 'csv')
        else:
            log = "csvUpload: ng, "
    except Exception:
        log = "pngUpload: fail, cvsUpload: fail, "
        pass
    print(source, sourceState)
    if (source == 0 or (source == 1 and sourceState == 'on')):
        print("Uploading to cloud")
        try:
            ip = findIP.main()
            #print("ip: {0}".format(ip))
        except Exception:
            pass
        try:
            cpu = measure_temp()
            #print("cpu: {0}".format(cpu))
        except Exception:
            pass
        updateSheet(unitID, ip, googlestamp, cpu, log, status)
        updatelog(unitID, ip, googlestamp, cpu, log, status)
    else:
        print("Skipping cloud")
        pass

    try:
        cleanFolder(IMG_DIR,10)
        cleanFolder(WEB_DIR,1)
        log = log + "folderClean: Complete "
    except Exception:
        log = log + "folderClean: Not Complete "
        pass
    return ('{0}'.format(imageName))

if __name__ == '__main__':
    main()
