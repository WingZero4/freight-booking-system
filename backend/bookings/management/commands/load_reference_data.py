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
        # Format: (code, name, country, region, port_type)
        # port_type: SEA = sea port, AIR = airport, BOTH = dual-use hub
        # Each code must be unique — cities with both sea and air use BOTH
        ports_data = [
            # ─── EAST ASIA — Sea Ports ───
            ('CNSHA', 'Shanghai', 'China', 'EAST_ASIA', 'SEA'),
            ('CNSZX', 'Shenzhen (Shekou)', 'China', 'EAST_ASIA', 'SEA'),
            ('CNNGB', 'Ningbo-Zhoushan', 'China', 'EAST_ASIA', 'SEA'),
            ('CNQDG', 'Qingdao', 'China', 'EAST_ASIA', 'SEA'),
            ('CNTXG', 'Tianjin (Xingang)', 'China', 'EAST_ASIA', 'SEA'),
            ('CNDLC', 'Dalian', 'China', 'EAST_ASIA', 'SEA'),
            ('CNXMN', 'Xiamen', 'China', 'EAST_ASIA', 'SEA'),
            ('CNGZG', 'Guangzhou (Nansha)', 'China', 'EAST_ASIA', 'SEA'),
            ('CNYTN', 'Yantian', 'China', 'EAST_ASIA', 'SEA'),
            ('CNLYG', 'Lianyungang', 'China', 'EAST_ASIA', 'SEA'),
            ('CNZUH', 'Zhuhai', 'China', 'EAST_ASIA', 'SEA'),
            ('CNFOC', 'Fuzhou', 'China', 'EAST_ASIA', 'SEA'),
            ('TWKHH', 'Kaohsiung', 'Taiwan', 'EAST_ASIA', 'SEA'),
            ('TWKEL', 'Keelung', 'Taiwan', 'EAST_ASIA', 'SEA'),
            ('TWTXG', 'Taichung', 'Taiwan', 'EAST_ASIA', 'SEA'),
            ('JPYOK', 'Yokohama', 'Japan', 'EAST_ASIA', 'SEA'),
            ('JPTYO', 'Tokyo', 'Japan', 'EAST_ASIA', 'SEA'),
            ('JPKOB', 'Kobe', 'Japan', 'EAST_ASIA', 'SEA'),
            ('JPNGO', 'Nagoya', 'Japan', 'EAST_ASIA', 'SEA'),
            ('JPOSA', 'Osaka', 'Japan', 'EAST_ASIA', 'SEA'),
            ('JPMOJ', 'Moji (Kitakyushu)', 'Japan', 'EAST_ASIA', 'SEA'),
            ('KRPUS', 'Busan', 'South Korea', 'EAST_ASIA', 'SEA'),
            ('KRINC', 'Incheon', 'South Korea', 'EAST_ASIA', 'SEA'),
            ('KRKAN', 'Gwangyang', 'South Korea', 'EAST_ASIA', 'SEA'),

            # ─── EAST ASIA — Dual-use Hubs ───
            ('HKHKG', 'Hong Kong', 'Hong Kong', 'EAST_ASIA', 'BOTH'),

            # ─── EAST ASIA — Airports ───
            ('CNPVG', 'Shanghai Pudong (PVG)', 'China', 'EAST_ASIA', 'AIR'),
            ('CNPEK', 'Beijing Capital (PEK)', 'China', 'EAST_ASIA', 'AIR'),
            ('CNCAN', 'Guangzhou Baiyun (CAN)', 'China', 'EAST_ASIA', 'AIR'),
            ('CNSXF', 'Shenzhen Bao\'an (SZX)', 'China', 'EAST_ASIA', 'AIR'),
            ('JPNRT', 'Tokyo Narita (NRT)', 'Japan', 'EAST_ASIA', 'AIR'),
            ('JPKIX', 'Osaka Kansai (KIX)', 'Japan', 'EAST_ASIA', 'AIR'),
            ('KRICN', 'Seoul Incheon (ICN)', 'South Korea', 'EAST_ASIA', 'AIR'),
            ('TWTPE', 'Taipei Taoyuan (TPE)', 'Taiwan', 'EAST_ASIA', 'AIR'),

            # ─── SOUTHEAST ASIA — Sea Ports ───
            ('MYTPP', 'Tanjung Pelepas', 'Malaysia', 'SOUTHEAST_ASIA', 'SEA'),
            ('MYPKG', 'Port Klang', 'Malaysia', 'SOUTHEAST_ASIA', 'SEA'),
            ('MYPEN', 'Penang', 'Malaysia', 'SOUTHEAST_ASIA', 'SEA'),
            ('THLCH', 'Laem Chabang', 'Thailand', 'SOUTHEAST_ASIA', 'SEA'),
            ('VNHPH', 'Hai Phong', 'Vietnam', 'SOUTHEAST_ASIA', 'SEA'),
            ('VNDAD', 'Da Nang', 'Vietnam', 'SOUTHEAST_ASIA', 'SEA'),
            ('IDSBP', 'Surabaya', 'Indonesia', 'SOUTHEAST_ASIA', 'SEA'),
            ('IDSRG', 'Semarang', 'Indonesia', 'SOUTHEAST_ASIA', 'SEA'),
            ('IDBLW', 'Belawan (Medan)', 'Indonesia', 'SOUTHEAST_ASIA', 'SEA'),
            ('PHCEB', 'Cebu', 'Philippines', 'SOUTHEAST_ASIA', 'SEA'),
            ('MMRGN', 'Yangon', 'Myanmar', 'SOUTHEAST_ASIA', 'SEA'),
            ('KHPNH', 'Phnom Penh', 'Cambodia', 'SOUTHEAST_ASIA', 'SEA'),
            ('KHSHV', 'Sihanoukville', 'Cambodia', 'SOUTHEAST_ASIA', 'SEA'),

            # ─── SOUTHEAST ASIA — Dual-use Hubs ───
            ('SGSIN', 'Singapore', 'Singapore', 'SOUTHEAST_ASIA', 'BOTH'),
            ('THBKK', 'Bangkok', 'Thailand', 'SOUTHEAST_ASIA', 'BOTH'),
            ('VNSGN', 'Ho Chi Minh City', 'Vietnam', 'SOUTHEAST_ASIA', 'BOTH'),
            ('IDJKT', 'Jakarta', 'Indonesia', 'SOUTHEAST_ASIA', 'BOTH'),
            ('PHMNL', 'Manila', 'Philippines', 'SOUTHEAST_ASIA', 'BOTH'),

            # ─── SOUTHEAST ASIA — Airports ───
            ('MYKUL', 'Kuala Lumpur (KUL)', 'Malaysia', 'SOUTHEAST_ASIA', 'AIR'),
            ('VNHAN', 'Hanoi Noi Bai (HAN)', 'Vietnam', 'SOUTHEAST_ASIA', 'AIR'),

            # ─── SOUTH ASIA — Sea Ports ───
            ('INNSA', 'Nhava Sheva (Mumbai)', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INMUN', 'Mundra', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INKOL', 'Kolkata', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INCOK', 'Cochin', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INTUT', 'Tuticorin', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INVTZ', 'Visakhapatnam', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INKRI', 'Krishnapatnam', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INGOA', 'Goa (Mormugao)', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INPAV', 'Pipavav', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INHZR', 'Hazira', 'India', 'SOUTH_ASIA', 'SEA'),
            ('INKTP', 'Kattupalli', 'India', 'SOUTH_ASIA', 'SEA'),
            ('PKQCT', 'Qasim (Port Muhammad Bin Qasim)', 'Pakistan', 'SOUTH_ASIA', 'SEA'),

            # ─── SOUTH ASIA — Dual-use Hubs ───
            ('INMAA', 'Chennai', 'India', 'SOUTH_ASIA', 'BOTH'),
            ('LKCMB', 'Colombo', 'Sri Lanka', 'SOUTH_ASIA', 'BOTH'),
            ('BDCGP', 'Chittagong', 'Bangladesh', 'SOUTH_ASIA', 'BOTH'),
            ('PKKAR', 'Karachi', 'Pakistan', 'SOUTH_ASIA', 'BOTH'),

            # ─── SOUTH ASIA — Airports ───
            ('INDEL', 'Delhi Indira Gandhi (DEL)', 'India', 'SOUTH_ASIA', 'AIR'),
            ('INBOM', 'Mumbai Chhatrapati Shivaji (BOM)', 'India', 'SOUTH_ASIA', 'AIR'),
            ('INBLR', 'Bangalore Kempegowda (BLR)', 'India', 'SOUTH_ASIA', 'AIR'),
            ('INHYD', 'Hyderabad Rajiv Gandhi (HYD)', 'India', 'SOUTH_ASIA', 'AIR'),
            ('BDDAC', 'Dhaka Hazrat Shahjalal (DAC)', 'Bangladesh', 'SOUTH_ASIA', 'AIR'),
            ('PKISB', 'Islamabad (ISB)', 'Pakistan', 'SOUTH_ASIA', 'AIR'),

            # ─── MIDDLE EAST — Sea Ports ───
            ('AEJEA', 'Jebel Ali (Dubai)', 'United Arab Emirates', 'MIDDLE_EAST', 'SEA'),
            ('SADMM', 'Dammam', 'Saudi Arabia', 'MIDDLE_EAST', 'SEA'),
            ('OMSLL', 'Salalah', 'Oman', 'MIDDLE_EAST', 'SEA'),
            ('OMSOH', 'Sohar', 'Oman', 'MIDDLE_EAST', 'SEA'),
            ('BHRUF', 'Khalifa Bin Salman', 'Bahrain', 'MIDDLE_EAST', 'SEA'),
            ('KWSAA', 'Shuwaikh', 'Kuwait', 'MIDDLE_EAST', 'SEA'),
            ('IQBSR', 'Basra', 'Iraq', 'MIDDLE_EAST', 'SEA'),
            ('TRMER', 'Mersin', 'Turkey', 'MIDDLE_EAST', 'SEA'),
            ('TRILH', 'Iskenderun', 'Turkey', 'MIDDLE_EAST', 'SEA'),
            ('ILHFA', 'Haifa', 'Israel', 'MIDDLE_EAST', 'SEA'),
            ('ILASH', 'Ashdod', 'Israel', 'MIDDLE_EAST', 'SEA'),
            ('JOAQJ', 'Aqaba', 'Jordan', 'MIDDLE_EAST', 'SEA'),

            # ─── MIDDLE EAST — Dual-use Hubs ───
            ('AEDXB', 'Dubai', 'United Arab Emirates', 'MIDDLE_EAST', 'BOTH'),
            ('AEAUH', 'Abu Dhabi', 'United Arab Emirates', 'MIDDLE_EAST', 'BOTH'),
            ('SAJED', 'Jeddah', 'Saudi Arabia', 'MIDDLE_EAST', 'BOTH'),
            ('TRIST', 'Istanbul', 'Turkey', 'MIDDLE_EAST', 'BOTH'),
            ('QADOH', 'Doha', 'Qatar', 'MIDDLE_EAST', 'BOTH'),

            # ─── MIDDLE EAST — Airports ───
            ('SARUH', 'Riyadh King Khalid (RUH)', 'Saudi Arabia', 'MIDDLE_EAST', 'AIR'),
            ('BHBAH', 'Bahrain (BAH)', 'Bahrain', 'MIDDLE_EAST', 'AIR'),
            ('OMSCT', 'Muscat (MCT)', 'Oman', 'MIDDLE_EAST', 'AIR'),

            # ─── EUROPE — Sea Ports ───
            ('NLRTM', 'Rotterdam', 'Netherlands', 'EUROPE', 'SEA'),
            ('DEHAM', 'Hamburg', 'Germany', 'EUROPE', 'SEA'),
            ('BEANR', 'Antwerp', 'Belgium', 'EUROPE', 'SEA'),
            ('DEBRV', 'Bremerhaven', 'Germany', 'EUROPE', 'SEA'),
            ('FRLEH', 'Le Havre', 'France', 'EUROPE', 'SEA'),
            ('FRFOS', 'Fos-sur-Mer (Marseille)', 'France', 'EUROPE', 'SEA'),
            ('GBFXT', 'Felixstowe', 'United Kingdom', 'EUROPE', 'SEA'),
            ('GBLGP', 'London Gateway', 'United Kingdom', 'EUROPE', 'SEA'),
            ('GBSOU', 'Southampton', 'United Kingdom', 'EUROPE', 'SEA'),
            ('GBLIV', 'Liverpool', 'United Kingdom', 'EUROPE', 'SEA'),
            ('ESBCN', 'Barcelona', 'Spain', 'EUROPE', 'SEA'),
            ('ESALG', 'Algeciras', 'Spain', 'EUROPE', 'SEA'),
            ('ESVLC', 'Valencia', 'Spain', 'EUROPE', 'SEA'),
            ('ITGOA', 'Genoa', 'Italy', 'EUROPE', 'SEA'),
            ('ITGIT', 'Gioia Tauro', 'Italy', 'EUROPE', 'SEA'),
            ('ITNAP', 'Naples', 'Italy', 'EUROPE', 'SEA'),
            ('ITLIV', 'Livorno', 'Italy', 'EUROPE', 'SEA'),
            ('GRPIR', 'Piraeus', 'Greece', 'EUROPE', 'SEA'),
            ('GRTHV', 'Thessaloniki', 'Greece', 'EUROPE', 'SEA'),
            ('PLGDY', 'Gdynia', 'Poland', 'EUROPE', 'SEA'),
            ('PLGDN', 'Gdansk', 'Poland', 'EUROPE', 'SEA'),
            ('SEGOT', 'Gothenburg', 'Sweden', 'EUROPE', 'SEA'),
            ('RULED', 'St. Petersburg', 'Russia', 'EUROPE', 'SEA'),
            ('RUVVO', 'Vladivostok', 'Russia', 'EUROPE', 'SEA'),
            ('PTLIS', 'Lisbon', 'Portugal', 'EUROPE', 'SEA'),
            ('PTSIE', 'Sines', 'Portugal', 'EUROPE', 'SEA'),
            ('MTMLA', 'Marsaxlokk', 'Malta', 'EUROPE', 'SEA'),
            ('FIRAU', 'Rauma', 'Finland', 'EUROPE', 'SEA'),
            ('FIHEL', 'Helsinki', 'Finland', 'EUROPE', 'SEA'),
            ('NOSVG', 'Stavanger', 'Norway', 'EUROPE', 'SEA'),
            ('NOOSL', 'Oslo', 'Norway', 'EUROPE', 'SEA'),
            ('DKAAR', 'Aarhus', 'Denmark', 'EUROPE', 'SEA'),
            ('IEDUB', 'Dublin', 'Ireland', 'EUROPE', 'SEA'),
            ('IECOR', 'Cork', 'Ireland', 'EUROPE', 'SEA'),
            ('HRRJK', 'Rijeka', 'Croatia', 'EUROPE', 'SEA'),
            ('SIKOP', 'Koper', 'Slovenia', 'EUROPE', 'SEA'),
            ('ROCND', 'Constanta', 'Romania', 'EUROPE', 'SEA'),

            # ─── EUROPE — Airports ───
            ('GBLHR', 'London Heathrow (LHR)', 'United Kingdom', 'EUROPE', 'AIR'),
            ('DEFRA', 'Frankfurt (FRA)', 'Germany', 'EUROPE', 'AIR'),
            ('NLAMS', 'Amsterdam Schiphol (AMS)', 'Netherlands', 'EUROPE', 'AIR'),
            ('FRCDG', 'Paris Charles de Gaulle (CDG)', 'France', 'EUROPE', 'AIR'),
            ('BEBRU', 'Brussels (BRU)', 'Belgium', 'EUROPE', 'AIR'),
            ('DELEJ', 'Leipzig/Halle (LEJ)', 'Germany', 'EUROPE', 'AIR'),
            ('LULUX', 'Luxembourg Findel (LUX)', 'Luxembourg', 'EUROPE', 'AIR'),
            ('ITMXP', 'Milan Malpensa (MXP)', 'Italy', 'EUROPE', 'AIR'),
            ('CHZRH', 'Zurich (ZRH)', 'Switzerland', 'EUROPE', 'AIR'),
            ('SEARN', 'Stockholm Arlanda (ARN)', 'Sweden', 'EUROPE', 'AIR'),
            ('DKCPH', 'Copenhagen Kastrup (CPH)', 'Denmark', 'EUROPE', 'AIR'),
            ('ESBCL', 'Barcelona El Prat (BCN)', 'Spain', 'EUROPE', 'AIR'),
            ('ATWIE', 'Vienna (VIE)', 'Austria', 'EUROPE', 'AIR'),

            # ─── NORTH AMERICA — Sea Ports ───
            ('USLGB', 'Long Beach', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USNYC', 'New York / New Jersey', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USSAV', 'Savannah', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USHOU', 'Houston', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USCHA', 'Charleston', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USBAL', 'Baltimore', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USTIW', 'Tacoma', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USSEA', 'Seattle', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USOAK', 'Oakland', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USMOB', 'Mobile', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USNOR', 'Norfolk', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USJAX', 'Jacksonville', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USPHF', 'Philadelphia', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USNWL', 'New Orleans', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('USPDX', 'Portland (Oregon)', 'United States', 'NORTH_AMERICA', 'SEA'),
            ('CAHAL', 'Halifax', 'Canada', 'NORTH_AMERICA', 'SEA'),
            ('CAMON', 'Montreal', 'Canada', 'NORTH_AMERICA', 'SEA'),
            ('CATPR', 'Prince Rupert', 'Canada', 'NORTH_AMERICA', 'SEA'),
            ('CATOR', 'Toronto (Hamilton)', 'Canada', 'NORTH_AMERICA', 'SEA'),
            ('MXMAN', 'Manzanillo', 'Mexico', 'NORTH_AMERICA', 'SEA'),
            ('MXLZC', 'Lazaro Cardenas', 'Mexico', 'NORTH_AMERICA', 'SEA'),
            ('MXVER', 'Veracruz', 'Mexico', 'NORTH_AMERICA', 'SEA'),
            ('MXALT', 'Altamira', 'Mexico', 'NORTH_AMERICA', 'SEA'),
            ('PAMIT', 'Manzanillo (Panama)', 'Panama', 'NORTH_AMERICA', 'SEA'),
            ('PAPCN', 'Balboa (Panama Canal)', 'Panama', 'NORTH_AMERICA', 'SEA'),
            ('DOHAI', 'Port of Haina', 'Dominican Republic', 'NORTH_AMERICA', 'SEA'),
            ('DOSDQ', 'Santo Domingo', 'Dominican Republic', 'NORTH_AMERICA', 'SEA'),
            ('JMKIN', 'Kingston', 'Jamaica', 'NORTH_AMERICA', 'SEA'),
            ('TTPOS', 'Port of Spain', 'Trinidad and Tobago', 'NORTH_AMERICA', 'SEA'),
            ('BSFPO', 'Freeport', 'Bahamas', 'NORTH_AMERICA', 'SEA'),
            ('GTPRQ', 'Puerto Quetzal', 'Guatemala', 'NORTH_AMERICA', 'SEA'),
            ('HNPCR', 'Puerto Cortes', 'Honduras', 'NORTH_AMERICA', 'SEA'),

            # ─── NORTH AMERICA — Dual-use Hubs ───
            ('USLAX', 'Los Angeles', 'United States', 'NORTH_AMERICA', 'BOTH'),
            ('USMIA', 'Miami', 'United States', 'NORTH_AMERICA', 'BOTH'),
            ('CAVAN', 'Vancouver', 'Canada', 'NORTH_AMERICA', 'BOTH'),

            # ─── NORTH AMERICA — Airports ───
            ('USJFK', 'New York JFK (JFK)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('USORD', 'Chicago O\'Hare (ORD)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('USATL', 'Atlanta Hartsfield (ATL)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('USDFW', 'Dallas/Fort Worth (DFW)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('USIAH', 'Houston Bush (IAH)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('USSFO', 'San Francisco (SFO)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('USMEM', 'Memphis (MEM)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('USSDF', 'Louisville (SDF)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('USANC', 'Anchorage (ANC)', 'United States', 'NORTH_AMERICA', 'AIR'),
            ('CAYYZ', 'Toronto Pearson (YYZ)', 'Canada', 'NORTH_AMERICA', 'AIR'),
            ('CAYUL', 'Montreal Trudeau (YUL)', 'Canada', 'NORTH_AMERICA', 'AIR'),
            ('CAYVR', 'Vancouver (YVR)', 'Canada', 'NORTH_AMERICA', 'AIR'),
            ('MXMEX', 'Mexico City (MEX)', 'Mexico', 'NORTH_AMERICA', 'AIR'),

            # ─── SOUTH AMERICA — Sea Ports ───
            ('BRSSZ', 'Santos', 'Brazil', 'SOUTH_AMERICA', 'SEA'),
            ('BRSFS', 'Sao Francisco do Sul', 'Brazil', 'SOUTH_AMERICA', 'SEA'),
            ('BRRIG', 'Rio Grande', 'Brazil', 'SOUTH_AMERICA', 'SEA'),
            ('BRPNG', 'Paranagua', 'Brazil', 'SOUTH_AMERICA', 'SEA'),
            ('BRITJ', 'Itajai (Navegantes)', 'Brazil', 'SOUTH_AMERICA', 'SEA'),
            ('BRSSA', 'Salvador', 'Brazil', 'SOUTH_AMERICA', 'SEA'),
            ('BRPEC', 'Suape (Recife)', 'Brazil', 'SOUTH_AMERICA', 'SEA'),
            ('BRMAO', 'Manaus', 'Brazil', 'SOUTH_AMERICA', 'SEA'),
            ('ARBUE', 'Buenos Aires', 'Argentina', 'SOUTH_AMERICA', 'SEA'),
            ('ARROS', 'Rosario', 'Argentina', 'SOUTH_AMERICA', 'SEA'),
            ('CLSAI', 'San Antonio', 'Chile', 'SOUTH_AMERICA', 'SEA'),
            ('CLVAP', 'Valparaiso', 'Chile', 'SOUTH_AMERICA', 'SEA'),
            ('CLSVE', 'San Vicente', 'Chile', 'SOUTH_AMERICA', 'SEA'),
            ('COBUN', 'Buenaventura', 'Colombia', 'SOUTH_AMERICA', 'SEA'),
            ('COCAR', 'Cartagena', 'Colombia', 'SOUTH_AMERICA', 'SEA'),
            ('PECLL', 'Callao', 'Peru', 'SOUTH_AMERICA', 'SEA'),
            ('ECGYE', 'Guayaquil', 'Ecuador', 'SOUTH_AMERICA', 'SEA'),
            ('UYMVD', 'Montevideo', 'Uruguay', 'SOUTH_AMERICA', 'SEA'),
            ('VELAG', 'La Guaira', 'Venezuela', 'SOUTH_AMERICA', 'SEA'),
            ('HTPAP', 'Port-au-Prince', 'Haiti', 'SOUTH_AMERICA', 'SEA'),

            # ─── SOUTH AMERICA — Airports ───
            ('BRGRU', 'Sao Paulo Guarulhos (GRU)', 'Brazil', 'SOUTH_AMERICA', 'AIR'),
            ('BRVCP', 'Campinas Viracopos (VCP)', 'Brazil', 'SOUTH_AMERICA', 'AIR'),
            ('AREZE', 'Buenos Aires Ezeiza (EZE)', 'Argentina', 'SOUTH_AMERICA', 'AIR'),
            ('CLSCL', 'Santiago (SCL)', 'Chile', 'SOUTH_AMERICA', 'AIR'),
            ('COBOG', 'Bogota El Dorado (BOG)', 'Colombia', 'SOUTH_AMERICA', 'AIR'),
            ('PELIM', 'Lima Jorge Chavez (LIM)', 'Peru', 'SOUTH_AMERICA', 'AIR'),
            ('ECUIO', 'Quito Mariscal Sucre (UIO)', 'Ecuador', 'SOUTH_AMERICA', 'AIR'),

            # ─── AFRICA — Sea Ports ───
            ('ZADUR', 'Durban', 'South Africa', 'AFRICA', 'SEA'),
            ('ZACPT', 'Cape Town', 'South Africa', 'AFRICA', 'SEA'),
            ('ZANGQ', 'Ngqura (Coega)', 'South Africa', 'AFRICA', 'SEA'),
            ('EGPSD', 'Port Said', 'Egypt', 'AFRICA', 'SEA'),
            ('EGALY', 'Alexandria', 'Egypt', 'AFRICA', 'SEA'),
            ('EGDAM', 'Damietta', 'Egypt', 'AFRICA', 'SEA'),
            ('MAPTM', 'Tanger Med', 'Morocco', 'AFRICA', 'SEA'),
            ('MACAS', 'Casablanca', 'Morocco', 'AFRICA', 'SEA'),
            ('NGAPP', 'Apapa (Lagos)', 'Nigeria', 'AFRICA', 'SEA'),
            ('NGTIN', 'Tin Can Island (Lagos)', 'Nigeria', 'AFRICA', 'SEA'),
            ('KEMBA', 'Mombasa', 'Kenya', 'AFRICA', 'SEA'),
            ('DJJIB', 'Djibouti', 'Djibouti', 'AFRICA', 'SEA'),
            ('TZDAR', 'Dar es Salaam', 'Tanzania', 'AFRICA', 'SEA'),
            ('GHTEM', 'Tema', 'Ghana', 'AFRICA', 'SEA'),
            ('CIABJ', 'Abidjan', 'Ivory Coast', 'AFRICA', 'SEA'),
            ('SNDAR', 'Dakar', 'Senegal', 'AFRICA', 'SEA'),
            ('MZMPN', 'Maputo', 'Mozambique', 'AFRICA', 'SEA'),
            ('AOLAD', 'Luanda', 'Angola', 'AFRICA', 'SEA'),
            ('CMDLE', 'Douala', 'Cameroon', 'AFRICA', 'SEA'),
            ('TNTUN', 'Tunis (Rades)', 'Tunisia', 'AFRICA', 'SEA'),

            # ─── AFRICA — Airports ───
            ('ZAJNB', 'Johannesburg OR Tambo (JNB)', 'South Africa', 'AFRICA', 'AIR'),
            ('KENBO', 'Nairobi Jomo Kenyatta (NBO)', 'Kenya', 'AFRICA', 'AIR'),
            ('EGCAI', 'Cairo (CAI)', 'Egypt', 'AFRICA', 'AIR'),
            ('ETADD', 'Addis Ababa Bole (ADD)', 'Ethiopia', 'AFRICA', 'AIR'),
            ('NGLOS', 'Lagos Murtala Muhammed (LOS)', 'Nigeria', 'AFRICA', 'AIR'),
            ('MACMN', 'Casablanca Mohammed V (CMN)', 'Morocco', 'AFRICA', 'AIR'),

            # ─── OCEANIA — Dual-use Hubs ───
            ('AUSYD', 'Sydney', 'Australia', 'OCEANIA', 'BOTH'),
            ('AUMEL', 'Melbourne', 'Australia', 'OCEANIA', 'BOTH'),
            ('AUBNE', 'Brisbane', 'Australia', 'OCEANIA', 'BOTH'),
            ('NZAKL', 'Auckland', 'New Zealand', 'OCEANIA', 'BOTH'),

            # ─── OCEANIA — Sea Ports ───
            ('AUFRE', 'Fremantle', 'Australia', 'OCEANIA', 'SEA'),
            ('AUADL', 'Adelaide', 'Australia', 'OCEANIA', 'SEA'),
            ('AUDWN', 'Darwin', 'Australia', 'OCEANIA', 'SEA'),
            ('NZTAU', 'Tauranga', 'New Zealand', 'OCEANIA', 'SEA'),
            ('NZLYT', 'Lyttelton', 'New Zealand', 'OCEANIA', 'SEA'),
            ('PGPOM', 'Port Moresby', 'Papua New Guinea', 'OCEANIA', 'SEA'),
            ('FJSUV', 'Suva', 'Fiji', 'OCEANIA', 'SEA'),
        ]

        created = 0
        updated = 0
        for code, name, country, region, port_type in ports_data:
            _, was_created = Port.objects.update_or_create(
                code=code,
                defaults={
                    'name': name, 'country': country,
                    'region': region, 'port_type': port_type,
                },
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
        # (code, name, size_ft, capacity_cbm, max_payload_kg)
        containers_data = [
            ('20GP', "20' General Purpose", 20, 33.0, 28200),
            ('40GP', "40' General Purpose", 40, 67.5, 28800),
            ('40HC', "40' High Cube", 40, 76.2, 28560),
            ('20RF', "20' Reefer", 20, 27.5, 27400),
            ('40RF', "40' Reefer", 40, 59.3, 27700),
            ('45HC', "45' High Cube", 45, 86.0, 27600),
            ('20OT', "20' Open Top", 20, 32.0, 28100),
            ('40OT', "40' Open Top", 40, 65.9, 28700),
            ('20FR', "20' Flat Rack", 20, 30.0, 28200),
            ('40FR', "40' Flat Rack", 40, 62.0, 40000),
        ]

        created = 0
        updated = 0
        for code, name, size_ft, capacity_cbm, max_payload_kg in containers_data:
            _, was_created = ContainerType.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'size_ft': size_ft,
                    'capacity_cbm': capacity_cbm,
                    'max_payload_kg': max_payload_kg,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
        self.stdout.write(f'  Container types: {created} created, {updated} updated')
