/** Ephemeral device location sent with geo queries (not cached from profile). */
export type ClientGeo = {
  label: string;
  latitude: number;
  longitude: number;
};

export function clientGeoWsFields(clientGeo?: ClientGeo | null) {
  return {
    client_location: clientGeo?.label ?? null,
    client_latitude: clientGeo?.latitude ?? null,
    client_longitude: clientGeo?.longitude ?? null,
  };
}
