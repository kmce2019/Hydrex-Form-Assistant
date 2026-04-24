import { haversineMiles } from './spatial';

export interface TceqRow {
  name: string;
  type: string;
  status?: string;
  latitude: number;
  longitude: number;
}

export function filterTceqByDistance(rows: TceqRow[], lat: number, lon: number) {
  return rows
    .map((row) => ({ ...row, distance_miles: haversineMiles(lat, lon, row.latitude, row.longitude) }))
    .filter((row) => row.distance_miles <= 1.0);
}
