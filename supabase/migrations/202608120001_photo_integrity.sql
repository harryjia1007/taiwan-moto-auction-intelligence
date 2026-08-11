-- A photo belongs to exactly one marketplace entity. This prevents a stale
-- association from making one cached image appear on two unrelated listings.

alter table photos
  add constraint photos_exactly_one_owner_chk
  check (num_nonnulls(vehicle_id, lot_id) = 1);

alter table photos
  add constraint photos_nonnegative_sort_order_chk
  check (sort_order >= 0);

comment on constraint photos_exactly_one_owner_chk on photos is
  'Cached official photo is owned by one vehicle or one inseparable bulk lot, never both.';
