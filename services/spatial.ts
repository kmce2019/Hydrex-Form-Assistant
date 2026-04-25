export const milesToMeters = (miles: number): number => miles * 1609.344;

export function haversineMiles(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const R = 3958.7613;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
}

export function buildBuffer(lat: number, lon: number, radiusMiles: number) {
  return {
    type: 'circle',
    center: { lat, lon },
    radius_miles: radiusMiles,
    radius_meters: milesToMeters(radiusMiles)
  };
}
