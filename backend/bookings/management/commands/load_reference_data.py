from django.core.management.base import BaseCommand
from bookings.models import Port, ContainerType, Carrier


class Command(BaseCommand):
    help = 'Load production reference data: ports, carriers, container types'

    def handle(self, *args, **options):
        self._load_ports()
        self._load_carriers()
        self._load_container_types()
        self.stdout.write(self.style.SUCCESS('Reference data loaded successfully.'))

    def _load_ports(self):
        ports_data = [
            # East Asia
            ('CNSHA', 'Shanghai', 'China', 'EAST_ASIA'),
            ('CNSZX', 'Shenzhen (Shekou)', 'China', 'EAST_ASIA'),
            ('CNNGB', 'Ningbo-Zhoushan', 'China', 'EAST_ASIA'),
            ('CNQDG', 'Qingdao', 'China', 'EAST_ASIA'),
            ('CNTXG', 'Tianjin (Xingang)', 'China', 'EAST_ASIA'),
            ('CNDLC', 'Dalian', 'China', 'EAST_ASIA'),
            ('CNXMN', 'Xiamen', 'China', 'EAST_ASIA'),
            ('CNGZG', 'Guangzhou (Nansha)', 'China', 'EAST_ASIA'),
            ('HKHKG', 'Hong Kong', 'Hong Kong', 'EAST_ASIA'),
            ('TWKHH', 'Kaohsiung', 'Taiwan', 'EAST_ASIA'),
            ('TWKEL', 'Keelung', 'Taiwan', 'EAST_ASIA'),
            ('JPYOK', 'Yokohama', 'Japan', 'EAST_ASIA'),
            ('JPTYO', 'Tokyo', 'Japan', 'EAST_ASIA'),
            ('JPKOB', 'Kobe', 'Japan', 'EAST_ASIA'),
            ('JPNGO', 'Nagoya', 'Japan', 'EAST_ASIA'),
            ('KRPUS', 'Busan', 'South Korea', 'EAST_ASIA'),
            ('KRINC', 'Incheon', 'South Korea', 'EAST_ASIA'),

            # Southeast Asia
            ('SGSIN', 'Singapore', 'Singapore', 'SOUTHEAST_ASIA'),
            ('MYTPP', 'Tanjung Pelepas', 'Malaysia', 'SOUTHEAST_ASIA'),
            ('MYPKG', 'Port Klang', 'Malaysia', 'SOUTHEAST_ASIA'),
            ('THLCH', 'Laem Chabang', 'Thailand', 'SOUTHEAST_ASIA'),
            ('THBKK', 'Bangkok', 'Thailand', 'SOUTHEAST_ASIA'),
            ('VNSGN', 'Ho Chi Minh City (Cat Lai)', 'Vietnam', 'SOUTHEAST_ASIA'),
            ('VNHPH', 'Hai Phong', 'Vietnam', 'SOUTHEAST_ASIA'),
            ('IDJKT', 'Jakarta (Tanjung Priok)', 'Indonesia', 'SOUTHEAST_ASIA'),
            ('IDSBP', 'Surabaya', 'Indonesia', 'SOUTHEAST_ASIA'),
            ('PHMNL', 'Manila', 'Philippines', 'SOUTHEAST_ASIA'),
            ('PHCEB', 'Cebu', 'Philippines', 'SOUTHEAST_ASIA'),
            ('MMRGN', 'Yangon', 'Myanmar', 'SOUTHEAST_ASIA'),
            ('KHPNH', 'Phnom Penh', 'Cambodia', 'SOUTHEAST_ASIA'),

            # South Asia
            ('INNSA', 'Nhava Sheva (Mumbai)', 'India', 'SOUTH_ASIA'),
            ('INMAA', 'Chennai', 'India', 'SOUTH_ASIA'),
            ('INMUN', 'Mundra', 'India', 'SOUTH_ASIA'),
            ('INKOL', 'Kolkata', 'India', 'SOUTH_ASIA'),
            ('INCOK', 'Cochin', 'India', 'SOUTH_ASIA'),
            ('LKCMB', 'Colombo', 'Sri Lanka', 'SOUTH_ASIA'),
            ('BDCGP', 'Chittagong', 'Bangladesh', 'SOUTH_ASIA'),
            ('PKKAR', 'Karachi', 'Pakistan', 'SOUTH_ASIA'),

            # Middle East
            ('AEJEA', 'Jebel Ali (Dubai)', 'United Arab Emirates', 'MIDDLE_EAST'),
            ('AEAUH', 'Abu Dhabi', 'United Arab Emirates', 'MIDDLE_EAST'),
            ('SAJED', 'Jeddah', 'Saudi Arabia', 'MIDDLE_EAST'),
            ('SADMM', 'Dammam', 'Saudi Arabia', 'MIDDLE_EAST'),
            ('OMSLL', 'Salalah', 'Oman', 'MIDDLE_EAST'),
            ('BHRUF', 'Khalifa Bin Salman', 'Bahrain', 'MIDDLE_EAST'),
            ('KWSAA', 'Shuwaikh', 'Kuwait', 'MIDDLE_EAST'),
            ('IQBSR', 'Basra', 'Iraq', 'MIDDLE_EAST'),
            ('TRIST', 'Istanbul (Ambarli)', 'Turkey', 'MIDDLE_EAST'),
            ('TRMER', 'Mersin', 'Turkey', 'MIDDLE_EAST'),
            ('ILHFA', 'Haifa', 'Israel', 'MIDDLE_EAST'),

            # Europe
            ('NLRTM', 'Rotterdam', 'Netherlands', 'EUROPE'),
            ('DEHAM', 'Hamburg', 'Germany', 'EUROPE'),
            ('BEANR', 'Antwerp', 'Belgium', 'EUROPE'),
            ('DEBRV', 'Bremerhaven', 'Germany', 'EUROPE'),
            ('FRLEH', 'Le Havre', 'France', 'EUROPE'),
            ('FRFOS', 'Fos-sur-Mer (Marseille)', 'France', 'EUROPE'),
            ('GBFXT', 'Felixstowe', 'United Kingdom', 'EUROPE'),
            ('GBLGP', 'London Gateway', 'United Kingdom', 'EUROPE'),
            ('GBSOU', 'Southampton', 'United Kingdom', 'EUROPE'),
            ('ESBCN', 'Barcelona', 'Spain', 'EUROPE'),
            ('ESALG', 'Algeciras', 'Spain', 'EUROPE'),
            ('ESVLC', 'Valencia', 'Spain', 'EUROPE'),
            ('ITGOA', 'Genoa', 'Italy', 'EUROPE'),
            ('ITGIT', 'Gioia Tauro', 'Italy', 'EUROPE'),
            ('GRPIR', 'Piraeus', 'Greece', 'EUROPE'),
            ('PLGDY', 'Gdynia', 'Poland', 'EUROPE'),
            ('PLGDN', 'Gdansk', 'Poland', 'EUROPE'),
            ('SEGOT', 'Gothenburg', 'Sweden', 'EUROPE'),
            ('RULED', 'St. Petersburg', 'Russia', 'EUROPE'),
            ('PTLIS', 'Lisbon', 'Portugal', 'EUROPE'),
            ('MTMLA', 'Marsaxlokk', 'Malta', 'EUROPE'),
            ('FIRAU', 'Rauma', 'Finland', 'EUROPE'),
            ('NOSVG', 'Stavanger', 'Norway', 'EUROPE'),

            # North America
            ('USLAX', 'Los Angeles', 'United States', 'NORTH_AMERICA'),
            ('USLGB', 'Long Beach', 'United States', 'NORTH_AMERICA'),
            ('USNYC', 'New York / New Jersey', 'United States', 'NORTH_AMERICA'),
            ('USSAV', 'Savannah', 'United States', 'NORTH_AMERICA'),
            ('USHOU', 'Houston', 'United States', 'NORTH_AMERICA'),
            ('USCHA', 'Charleston', 'United States', 'NORTH_AMERICA'),
            ('USBAL', 'Baltimore', 'United States', 'NORTH_AMERICA'),
            ('USTIW', 'Tacoma', 'United States', 'NORTH_AMERICA'),
            ('USSEA', 'Seattle', 'United States', 'NORTH_AMERICA'),
            ('USOAK', 'Oakland', 'United States', 'NORTH_AMERICA'),
            ('USMIA', 'Miami', 'United States', 'NORTH_AMERICA'),
            ('USMOB', 'Mobile', 'United States', 'NORTH_AMERICA'),
            ('USNOR', 'Norfolk', 'United States', 'NORTH_AMERICA'),
            ('CAVAN', 'Vancouver', 'Canada', 'NORTH_AMERICA'),
            ('CAHAL', 'Halifax', 'Canada', 'NORTH_AMERICA'),
            ('CAMON', 'Montreal', 'Canada', 'NORTH_AMERICA'),
            ('CATPR', 'Prince Rupert', 'Canada', 'NORTH_AMERICA'),
            ('MXMAN', 'Manzanillo', 'Mexico', 'NORTH_AMERICA'),
            ('MXLZC', 'Lazaro Cardenas', 'Mexico', 'NORTH_AMERICA'),
            ('MXVER', 'Veracruz', 'Mexico', 'NORTH_AMERICA'),
            ('PAMIT', 'Manzanillo (Panama)', 'Panama', 'NORTH_AMERICA'),
            ('PAPCN', 'Balboa (Panama Canal)', 'Panama', 'NORTH_AMERICA'),

            # South America
            ('BRSSZ', 'Santos', 'Brazil', 'SOUTH_AMERICA'),
            ('BRSFS', 'Sao Francisco do Sul', 'Brazil', 'SOUTH_AMERICA'),
            ('BRRIG', 'Rio Grande', 'Brazil', 'SOUTH_AMERICA'),
            ('BRPNG', 'Paranagua', 'Brazil', 'SOUTH_AMERICA'),
            ('ARBUE', 'Buenos Aires', 'Argentina', 'SOUTH_AMERICA'),
            ('CLSAI', 'San Antonio', 'Chile', 'SOUTH_AMERICA'),
            ('CLVAP', 'Valparaiso', 'Chile', 'SOUTH_AMERICA'),
            ('COBUN', 'Buenaventura', 'Colombia', 'SOUTH_AMERICA'),
            ('COCAR', 'Cartagena', 'Colombia', 'SOUTH_AMERICA'),
            ('PECLL', 'Callao', 'Peru', 'SOUTH_AMERICA'),
            ('ECGYE', 'Guayaquil', 'Ecuador', 'SOUTH_AMERICA'),
            ('UYMVD', 'Montevideo', 'Uruguay', 'SOUTH_AMERICA'),

            # Africa
            ('ZADUR', 'Durban', 'South Africa', 'AFRICA'),
            ('ZACPT', 'Cape Town', 'South Africa', 'AFRICA'),
            ('EGPSD', 'Port Said', 'Egypt', 'AFRICA'),
            ('MAPTM', 'Tanger Med', 'Morocco', 'AFRICA'),
            ('NGAPP', 'Apapa (Lagos)', 'Nigeria', 'AFRICA'),
            ('KEMBA', 'Mombasa', 'Kenya', 'AFRICA'),
            ('DJJIB', 'Djibouti', 'Djibouti', 'AFRICA'),
            ('TZDAR', 'Dar es Salaam', 'Tanzania', 'AFRICA'),
            ('GHTEM', 'Tema', 'Ghana', 'AFRICA'),
            ('CIABJ', 'Abidjan', 'Ivory Coast', 'AFRICA'),

            # Oceania
            ('AUMEL', 'Melbourne', 'Australia', 'OCEANIA'),
            ('AUSYD', 'Sydney', 'Australia', 'OCEANIA'),
            ('AUBNE', 'Brisbane', 'Australia', 'OCEANIA'),
            ('AUFRE', 'Fremantle', 'Australia', 'OCEANIA'),
            ('NZAKL', 'Auckland', 'New Zealand', 'OCEANIA'),
            ('NZTAU', 'Tauranga', 'New Zealand', 'OCEANIA'),
        ]

        created = 0
        updated = 0
        for code, name, country, region in ports_data:
            _, was_created = Port.objects.update_or_create(
                code=code,
                defaults={'name': name, 'country': country, 'region': region},
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(f'  Ports: {created} created, {updated} updated')

    def _load_carriers(self):
        carriers_data = [
            # Ocean carriers
            ('MAEU', 'Maersk', 'OCEAN'),
            ('MSCU', 'MSC - Mediterranean Shipping Co', 'OCEAN'),
            ('CMDU', 'CMA CGM', 'OCEAN'),
            ('HLCU', 'Hapag-Lloyd', 'OCEAN'),
            ('ONEY', 'ONE (Ocean Network Express)', 'OCEAN'),
            ('EGLV', 'Evergreen Line', 'OCEAN'),
            ('COSU', 'COSCO Shipping Lines', 'OCEAN'),
            ('YMLU', 'Yang Ming Marine Transport', 'OCEAN'),
            ('ZIMU', 'ZIM Integrated Shipping', 'OCEAN'),
            ('HDMU', 'HMM (Hyundai Merchant Marine)', 'OCEAN'),
            ('WHLC', 'Wan Hai Lines', 'OCEAN'),
            ('PILU', 'PIL (Pacific International Lines)', 'OCEAN'),
            ('SMLM', 'SM Line', 'OCEAN'),
            ('SUDU', 'Hamburg Sud', 'OCEAN'),
            ('ANNU', 'ANL Container Line', 'OCEAN'),

            # Air carriers
            ('LH', 'Lufthansa Cargo', 'AIR'),
            ('EK', 'Emirates SkyCargo', 'AIR'),
            ('SQ', 'Singapore Airlines Cargo', 'AIR'),
            ('CX', 'Cathay Pacific Cargo', 'AIR'),
            ('BA', 'IAG Cargo (British Airways)', 'AIR'),
            ('BR', 'EVA Air Cargo', 'AIR'),
            ('KE', 'Korean Air Cargo', 'AIR'),
            ('TK', 'Turkish Airlines Cargo', 'AIR'),
            ('QR', 'Qatar Airways Cargo', 'AIR'),
            ('CI', 'China Airlines Cargo', 'AIR'),
            ('CA', 'Air China Cargo', 'AIR'),
            ('NH', 'ANA Cargo', 'AIR'),
            ('FX', 'FedEx Express', 'AIR'),
            ('5X', 'UPS Airlines', 'AIR'),
            ('CV', 'Cargolux', 'AIR'),
        ]

        created = 0
        updated = 0
        for scac_code, name, carrier_type in carriers_data:
            _, was_created = Carrier.objects.update_or_create(
                scac_code=scac_code,
                defaults={'name': name, 'carrier_type': carrier_type},
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(f'  Carriers: {created} created, {updated} updated')

    def _load_container_types(self):
        containers_data = [
            ('20GP', "20' General Purpose", 20),
            ('40GP', "40' General Purpose", 40),
            ('40HC', "40' High Cube", 40),
            ('20RF', "20' Reefer", 20),
            ('40RF', "40' Reefer", 40),
            ('45HC', "45' High Cube", 45),
            ('20OT', "20' Open Top", 20),
            ('40OT', "40' Open Top", 40),
            ('20FR', "20' Flat Rack", 20),
            ('40FR', "40' Flat Rack", 40),
        ]

        created = 0
        updated = 0
        for code, name, size_ft in containers_data:
            _, was_created = ContainerType.objects.update_or_create(
                code=code,
                defaults={'name': name, 'size_ft': size_ft},
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(f'  Container types: {created} created, {updated} updated')
