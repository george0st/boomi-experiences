# How do I get started?

## 1. Prepare your environment 

### 1.1 Clone boomi-experiences

 - You can use many of github clients such as [GitHub Desktop](https://desktop.github.com/download/),
   ... or clients embeddit in your developer tools.
 - It contains also the python project **boom-care**.

### 1.2 Install python 
 - You can focus on version **3.11 or higher**, see [Python Download](https://www.python.org/downloads/)
 - We tested Python version 3.11 and 3.14

### 1.2 Install addition python libraries

 - It is useful to update **pip** to the last version
   - `python.exe -m pip install --upgrade pip`
 - These libraries are needed for correct python run
   - `pip install -r ./boomi-care/requirements.txt`

## 2. Setup Boomi access

Update the file **setting.env** and define these three items for connection to the Boomi:

 - `BOOMI_ACCOUNT = <boomi account e.g. 'london-OFTM0E'>`
 - `BOOMI_USER    = <boomi token e.g. 'BOOMI_TOKEN.john@london.uk'>`
 - `BOOMI_SECRET  = <guid e.g. '851e2bf1-0870-4358-8c91-ec147e568b8'>`

## 3. Run prepared scripts

### 3.1 Switch to relevant dir

 - The switch do directory with *.bat scripts
   - `cd boomi-care/helper`

### 3.2 Run scripts
  
 - The run these scripts

   - `./00-security.bat`
   - `./01-deployed.bat`
   - `./02-schedule.bat`
   - ...
  
## 4. Check outputs

 - See the directory with outputs `cd boomi-care/output`