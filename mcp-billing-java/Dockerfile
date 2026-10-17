FROM --platform=linux/arm64 public.ecr.aws/docker/library/maven:3.9-amazoncorretto-21 AS build
WORKDIR /src
COPY pom.xml .
RUN mvn -q dependency:go-offline
COPY src ./src
RUN mvn -q -DskipTests package

FROM --platform=linux/arm64 public.ecr.aws/amazoncorretto/amazoncorretto:21-al2023-headless
WORKDIR /app
COPY --from=build /src/target/mcp-billing-0.1.0.jar app.jar
RUN dnf -y install shadow-utils && useradd -u 1000 app && dnf clean all
USER app
ENV SPRING_PROFILES_ACTIVE=aws PORT=8000
EXPOSE 8000
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app/app.jar"]
