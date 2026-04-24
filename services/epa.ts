export interface EpaFacility {
  name: string;
  type: string;
  status: string;
  distance_miles?: number;
}

export async function queryEpaEcho(lat: number, lon: number, radiusMiles = 0.5) {
  const params = new URLSearchParams({ p_lat: String(lat), p_long: String(lon), p_dist: String(radiusMiles), output: 'JSON' });
  const res = await fetch(`https://echo.epa.gov/tools/data-downloads/frs-facility-search?${params.toString()}`);
  if (!res.ok) throw new Error(`EPA ECHO request failed: ${res.status}`);
  return res.json();
}
