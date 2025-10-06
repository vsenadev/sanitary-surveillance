Minimal Requirements
Before running the project, make sure you have the following installed:

Python 3.9+ (with libraries listed in requirements.txt)

Google Chrome

Docker & Docker Compose

Project Description
This project collects product recall and safety warning data from the CPSC (Consumer Product Safety Commission) website, processes the information, organizes it into a JSON format, and persists it in InterSystems IRIS.

The project includes:

A Python scraper using Selenium for automatic CSV downloads.

Data processing and cleaning, normalizing names of manufacturers, importers, and retailers.

Persistence in InterSystems IRIS, with automatic creation of main and auxiliary tables.

Daily data collection scheduled for 10:00 PM (22:00) using schedule.

Technologies Used
Python (Selenium, Pandas, Schedule)

InterSystems IRIS (Community Edition via Docker)

Docker & Docker Compose

JSON and CSV for temporary storage

Project Structure
.
├── api.py
├── cpsc_scraper.py
├── dashboard.py
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── iris.script
├── requirements.txt
├── processed_cpsc_data.json
├── downloads/              # Temporarily downloaded CSVs
├── storage/                # Persistent IRIS data
└── .env
How to Run
Clone the repository:

Bash

git clone <REPOSITORY_URL>
cd <REPOSITORY_NAME>
Install Python dependencies:

Bash

pip install -r requirements.txt
Execute Docker Compose:

Bash

docker compose up --build -d
This command will start the container with InterSystems IRIS, process the collected data, and store it automatically.

The main script is already configured to run daily at 10:00 PM (22:00). To run manually:

```bash
python cpsc_scraper.py
```
How It Works
The scraper accesses the CPSC page and downloads the Recalls and Product Safety Warnings CSVs.

The CSV files are processed, extracting information such as products, manufacturers, importers, distributors, retailers, and countries of manufacture.

The data is inserted into the main table cpsc_data and auxiliary tables (cpsc_sold_at, cpsc_importers, cpsc_manufacturers, etc.) in IRIS.

After processing, the temporary CSVs are removed, and the data becomes available in IRIS for SQL queries or dashboard use.

Main Command
Bash

docker compose up --build -d
This command is sufficient to build the image, start the container, and process the data automatically.

Next Steps
Add dashboard images and examples of IRIS queries.

Publish a demo video or GIF showing the scraper in action.

License
This project is Open Source and can be used under the terms of the MIT license.