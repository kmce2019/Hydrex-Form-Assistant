export async function geocodeAddress(query: string) {
  const params = new URLSearchParams({ q: query, format: 'json', limit: '1' });
  const res = await fetch(`https://nominatim.openstreetmap.org/search?${params.toString()}`, {
    headers: { 'Accept': 'application/json' }
  });
  if (!res.ok) throw new Error(`Geocode request failed: ${res.status}`);
  const data = await res.json();
  if (!data?.length) throw new Error('No geocode match found');
  return { latitude: Number(data[0].lat), longitude: Number(data[0].lon), display_name: data[0].display_name };
}
