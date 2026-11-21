-- =====================================================================
-- V001 · Plataforma comercial IoT (práctica 4.3)
-- Base: vehiculo_iot (Amazon RDS MySQL 8.4)
--
-- Agrega: roles, usuarios, modelos, asignaciones, sesiones y auditoría.
-- Altera: vehiculos (unidad física), comandos, demos e historial_comandos.
-- NO borra tablas, filas ni cambia IDs existentes.
--
-- IMPORTANTE: en MySQL cada CREATE/ALTER hace COMMIT implícito, así que
-- NO hay ROLLBACK automático. La reversión es el script V001_DOWN.sql
-- y, en último caso, el snapshot "respaldo-antes-4-3" de RDS.
-- Aplicar SIEMPRE primero en la copia vehiculo_iot_prueba.
-- =====================================================================

-- 1. Roles de cuentas con credenciales (el Invitado NO tiene cuenta)
CREATE TABLE roles (
  id_rol      TINYINT UNSIGNED NOT NULL,
  nombre      VARCHAR(20)  NOT NULL,
  descripcion VARCHAR(120) NULL,
  PRIMARY KEY (id_rol),
  UNIQUE KEY uq_rol_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO roles (id_rol, nombre, descripcion) VALUES
  (1, 'ADMIN',   'Empresa comercializadora: inventario, clientes, asignaciones y demos de fábrica'),
  (2, 'USUARIO', 'Cliente comprador: opera y monitorea solo sus unidades');

-- 2. Usuarios / clientes (la contraseña se guarda como hash PBKDF2, nunca en texto)
CREATE TABLE usuarios (
  id_usuario     INT NOT NULL AUTO_INCREMENT,
  id_rol         TINYINT UNSIGNED NOT NULL,
  nombre         VARCHAR(100) NOT NULL,
  correo         VARCHAR(120) NOT NULL,
  telefono       VARCHAR(20)  NULL,
  password_hash  VARCHAR(255) NOT NULL,
  activo         TINYINT(1)   NOT NULL DEFAULT 1,
  fecha_registro TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ultimo_acceso  TIMESTAMP    NULL DEFAULT NULL,
  PRIMARY KEY (id_usuario),
  UNIQUE KEY uq_usuario_correo (correo),
  KEY idx_usuario_rol (id_rol),
  CONSTRAINT fk_usuario_rol FOREIGN KEY (id_rol) REFERENCES roles (id_rol)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 3. Modelos comerciales (catálogo); distinto de la UNIDAD física
CREATE TABLE modelos (
  id_modelo        INT NOT NULL AUTO_INCREMENT,
  nombre           VARCHAR(80)  NOT NULL,
  descripcion      VARCHAR(255) NULL,
  microcontrolador VARCHAR(50)  NULL,
  imagen           VARCHAR(255) NULL,
  publicado        TINYINT(1)   NOT NULL DEFAULT 1,
  activo           TINYINT(1)   NOT NULL DEFAULT 1,
  fecha_registro   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id_modelo),
  UNIQUE KEY uq_modelo_nombre (nombre)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 4. vehiculos pasa a representar la UNIDAD física (se conserva id_vehiculo = ID de Control)
ALTER TABLE vehiculos
  ADD COLUMN id_modelo        INT NULL AFTER modelo,
  ADD COLUMN numero_serie     VARCHAR(40) NULL AFTER id_modelo,
  ADD COLUMN estado_comercial ENUM('DISPONIBLE','VENDIDO','EXHIBICION','INACTIVO') NOT NULL DEFAULT 'DISPONIBLE' AFTER numero_serie,
  ADD COLUMN id_propietario   INT NULL AFTER estado_comercial,
  ADD COLUMN soporte_hasta    DATETIME NULL AFTER id_propietario,
  ADD COLUMN dispositivo_hash CHAR(64) NULL AFTER soporte_hasta;

-- 4.1 Migración de datos: el vehículo actual se vuelve modelo + unidad de exhibición
INSERT INTO modelos (nombre, descripcion, microcontrolador)
SELECT v.nombre, MAX(v.descripcion), MAX(v.microcontrolador)
  FROM vehiculos v
 GROUP BY v.nombre;

UPDATE vehiculos v
  JOIN modelos m ON m.nombre = v.nombre
   SET v.id_modelo        = m.id_modelo,
       v.numero_serie     = CONCAT('EXC-', LPAD(v.id_vehiculo, 4, '0')),
       v.estado_comercial = IF(v.activo = 1, 'EXHIBICION', 'INACTIVO');

-- 4.2 Ya con datos: obligatorios, únicos, índices y llaves foráneas
ALTER TABLE vehiculos
  MODIFY COLUMN id_modelo    INT NOT NULL,
  MODIFY COLUMN numero_serie VARCHAR(40) NOT NULL,
  ADD UNIQUE KEY uq_vehiculo_serie (numero_serie),
  ADD KEY idx_vehiculo_modelo (id_modelo),
  ADD KEY idx_vehiculo_propietario (id_propietario),
  ADD KEY idx_vehiculo_estado (estado_comercial),
  ADD CONSTRAINT fk_vehiculo_modelo FOREIGN KEY (id_modelo) REFERENCES modelos (id_modelo)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  ADD CONSTRAINT fk_vehiculo_propietario FOREIGN KEY (id_propietario) REFERENCES usuarios (id_usuario)
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- 5. Comandos: cuáles puede usar un Invitado (lista reducida)
ALTER TABLE comandos
  ADD COLUMN permitido_invitado TINYINT(1) NOT NULL DEFAULT 0 AFTER activo;

-- Avanzar, retroceder, girar, DETENER, sonido y LED (sin brazo, pala ni DEMO)
UPDATE comandos SET permitido_invitado = 1 WHERE codigo IN (1, 2, 3, 4, 9, 10, 11);

-- 6. Demos de fábrica (empresa) y privadas (comprador)
ALTER TABLE demos
  ADD COLUMN tipo           ENUM('FABRICA','PRIVADA') NOT NULL DEFAULT 'FABRICA' AFTER descripcion,
  ADD COLUMN id_propietario INT NULL AFTER tipo,
  ADD COLUMN fecha_creacion TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP AFTER activo,
  ADD KEY idx_demo_propietario (id_propietario),
  ADD CONSTRAINT fk_demo_propietario FOREIGN KEY (id_propietario) REFERENCES usuarios (id_usuario)
    ON DELETE RESTRICT ON UPDATE CASCADE;

-- 7. Historial de asignaciones (ventas y reasignaciones); nunca se borra
CREATE TABLE asignaciones (
  id_asignacion INT NOT NULL AUTO_INCREMENT,
  id_vehiculo   INT NOT NULL,
  id_usuario    INT NOT NULL,
  id_admin      INT NULL,
  fecha_inicio  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  fecha_fin     TIMESTAMP NULL DEFAULT NULL,
  motivo        VARCHAR(150) NULL,
  PRIMARY KEY (id_asignacion),
  KEY idx_asig_vehiculo (id_vehiculo, fecha_fin),
  KEY idx_asig_usuario (id_usuario, fecha_fin),
  KEY idx_asig_admin (id_admin),
  CONSTRAINT fk_asig_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos (id_vehiculo)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_asig_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario)
    ON DELETE RESTRICT ON UPDATE CASCADE,
  CONSTRAINT fk_asig_admin FOREIGN KEY (id_admin) REFERENCES usuarios (id_usuario)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 8. Sesiones: login de cuentas y sesiones temporales de Invitado con reserva
--    (se guarda solo el SHA-256 del token, nunca el token)
CREATE TABLE sesiones (
  id_sesion     BIGINT NOT NULL AUTO_INCREMENT,
  token_hash    CHAR(64) NOT NULL,
  tipo          ENUM('USUARIO','INVITADO') NOT NULL,
  id_usuario    INT NULL,
  id_vehiculo   INT NULL,
  alias         VARCHAR(60) NULL,
  creada        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expira        DATETIME NOT NULL,
  cerrada       DATETIME NULL,
  motivo_cierre VARCHAR(40) NULL,
  PRIMARY KEY (id_sesion),
  UNIQUE KEY uq_sesion_token (token_hash),
  KEY idx_sesion_usuario (id_usuario),
  KEY idx_sesion_reserva (id_vehiculo, tipo, cerrada, expira),
  CONSTRAINT fk_sesion_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario)
    ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT fk_sesion_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos (id_vehiculo)
    ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 9. Auditoría de acciones sensibles (sin contraseñas ni tokens)
CREATE TABLE auditoria (
  id_auditoria BIGINT NOT NULL AUTO_INCREMENT,
  fecha        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  id_usuario   INT NULL,
  actor        VARCHAR(120) NOT NULL,
  rol          VARCHAR(20)  NOT NULL,
  accion       VARCHAR(60)  NOT NULL,
  recurso      VARCHAR(40)  NOT NULL,
  id_recurso   VARCHAR(40)  NULL,
  resultado    ENUM('EXITO','RECHAZADO','ERROR') NOT NULL,
  detalle      VARCHAR(255) NULL,
  PRIMARY KEY (id_auditoria),
  KEY idx_aud_fecha (fecha),
  KEY idx_aud_usuario (id_usuario),
  CONSTRAINT fk_aud_usuario FOREIGN KEY (id_usuario) REFERENCES usuarios (id_usuario)
    ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- 10. Historial: índice para los 10 más recientes y protección contra borrado
ALTER TABLE historial_comandos
  ADD KEY idx_historial_vehiculo_fecha (id_vehiculo, fecha_hora, id_historial);

-- Antes: borrar un vehículo borraba su historial (ON DELETE CASCADE).
-- Ahora: RESTRICT (las unidades se dan de baja lógica, no se borran).
ALTER TABLE historial_comandos DROP FOREIGN KEY fk_historial_vehiculo;
ALTER TABLE historial_comandos
  ADD CONSTRAINT fk_historial_vehiculo FOREIGN KEY (id_vehiculo) REFERENCES vehiculos (id_vehiculo)
    ON DELETE RESTRICT ON UPDATE CASCADE;
