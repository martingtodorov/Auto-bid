// Comprehensive list of car makes (mobile.de catalogue)
export const CAR_MAKES = [
  "Abarth", "AC", "Acura", "Aixam", "Alfa Romeo", "Alpina", "Alpine", "Aro", "Artega",
  "Asia Motors", "Aston Martin", "Audi", "Austin", "Austin Healey",
  "Baic", "Barkas", "Bentley", "BMW", "Borgward", "Brilliance", "Bugatti", "Buick", "BYD",
  "Cadillac", "Casalini", "Caterham", "Chatenet", "Chevrolet", "Chrysler", "Citroën",
  "Cobra", "Corvette", "Cupra",
  "Dacia", "Daewoo", "DAF", "Daihatsu", "Daimler", "Datsun", "De Tomaso", "DeLorean",
  "DFSK", "Dodge", "Dong Feng", "Donkervoort", "DS Automobiles",
  "e.GO", "Elaris", "Estrima",
  "Ferrari", "Fiat", "Fisker", "Ford",
  "GAC Gonow", "Genesis", "GMC", "Great Wall", "Grecav",
  "Hamann", "Holden", "Honda", "Hongqi", "Hummer", "Hyundai",
  "Ineos", "Infiniti", "Isuzu", "Iveco",
  "Jaguar", "Jeep",
  "KGM", "Kia", "Koenigsegg", "KTM",
  "Lada", "Lamborghini", "Lancia", "Land Rover", "Landwind", "Leapmotor", "Lexus",
  "Ligier", "Lincoln", "LondonEV", "Lotus", "Lucid", "Lynk & Co",
  "Mahindra", "Maserati", "Maybach", "Mazda", "McLaren", "Mercedes-Benz", "MG",
  "Microcar", "MINI", "Mitsubishi", "Morgan",
  "NIO", "Nissan", "Noble",
  "Oldsmobile", "Opel",
  "Pagani", "Peugeot", "Piaggio", "Plymouth", "Polestar", "Pontiac", "Porsche", "Puch",
  "Renault", "Rimac", "Rolls-Royce", "Rover",
  "Saab", "Santana", "Seat", "Seres", "Skoda", "Smart", "Ssangyong", "Subaru", "Suzuki",
  "Talbot", "Tata", "Tazzari", "Tesla", "Toyota", "Trabant", "Triumph", "TVR",
  "Volkswagen", "Volvo", "Voyah",
  "Wartburg", "Westfield", "Wiesmann",
  "Xpeng",
  "Zastava", "Zhidou",
];

export const mergeMakes = (extra = []) => {
  const set = new Set([...CAR_MAKES, ...extra.filter(Boolean)]);
  return Array.from(set).sort((a, b) => a.localeCompare(b, "bg"));
};
