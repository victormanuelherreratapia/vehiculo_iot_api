-- =====================================================================
-- V001 DOWN · Reversión razonable de V001 (para entorno de PRUEBA)
-- Deja las 6 tablas originales como estaban. Los datos creados después
-- de la migración en las tablas nuevas (usuarios, sesiones, auditoría,
-- asignaciones, modelos) SE PIERDEN: en producción se prefiere restaurar
-- el snapshot "respaldo-antes-4-3".
-- =====================================================================

-- 10. Historial: vuelve la llave original y se quita el índice
ALTER TABLE historial_comandos DROP FOREIGN KEY fk_historial_vehiculo;
ALTER TABLE historial_comandos
  ADD CONSTRAINT fk_historial_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos (id_vehiculo)
    ON DELETE CASCADE ON UPDATE CASCADE;
ALTER TABLE historial_comandos DROP INDEX idx_historial_vehiculo_fecha;

-- 9, 8, 7. Tablas nuevas dependientes
DROP TABLE IF EXISTS auditoria;
DROP TABLE IF EXISTS sesiones;
DROP TABLE IF EXISTS asignaciones;

-- 6. Demos
ALTER TABLE demos DROP FOREIGN KEY fk_demo_propietario;
ALTER TABLE demos
  DROP INDEX idx_demo_propietario,
  DROP COLUMN fecha_creacion,
  DROP COLUMN id_propietario,
  DROP COLUMN tipo;

-- 5. Comandos
ALTER TABLE comandos DROP COLUMN permitido_invitado;

-- 4. Vehículos
ALTER TABLE vehiculos DROP FOREIGN KEY fk_vehiculo_propietario;
ALTER TABLE vehiculos DROP FOREIGN KEY fk_vehiculo_modelo;
ALTER TABLE vehiculos
  DROP INDEX uq_vehiculo_serie,
  DROP INDEX idx_vehiculo_modelo,
  DROP INDEX idx_vehiculo_propietario,
  DROP INDEX idx_vehiculo_estado,
  DROP COLUMN dispositivo_hash,
  DROP COLUMN soporte_hasta,
  DROP COLUMN id_propietario,
  DROP COLUMN estado_comercial,
  DROP COLUMN numero_serie,
  DROP COLUMN id_modelo;

-- 3, 2, 1. Catálogos nuevos
DROP TABLE IF EXISTS modelos;
DROP TABLE IF EXISTS usuarios;
DROP TABLE IF EXISTS roles;
